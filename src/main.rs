use std::env;
use std::ffi::{OsStr, OsString};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

#[cfg(unix)]
use std::os::unix::process::CommandExt;
#[cfg(not(unix))]
use std::process::ExitStatus;

const DEFAULT_PYTHON: Option<&str> = option_env!("MINIVIKING_DEFAULT_PYTHON");
const DEFAULT_SOURCE: Option<&str> = option_env!("MINIVIKING_DEFAULT_SOURCE");
const SERVER_ROLE: &str = "miniviking-server";
const LLM_ROLE: &str = "miniviking-llm";
const EMBED_ROLE: &str = "miniviking-embed";
const ROLE_COMMANDS: [&str; 3] = [SERVER_ROLE, LLM_ROLE, EMBED_ROLE];

fn main() {
    std::process::exit(run());
}

fn run() -> i32 {
    let args: Vec<OsString> = env::args_os().skip(1).collect();
    let role = process_role(&args);
    let source_root = match python_source_root() {
        Ok(path) => path,
        Err(error) => {
            eprintln!("miniviking: {error}");
            return 1;
        }
    };
    let python = python_command();
    let runner = if command_requires_bootstrap(&args) {
        match ensure_runtime(&python, &source_root) {
            Ok(path) => path.into_os_string(),
            Err(error) => {
                eprintln!("miniviking: {error}");
                return 1;
            }
        }
    } else {
        python
    };
    let runner = role_python_runner(runner, role);

    let mut command = Command::new(runner);
    command.arg("-m").arg("miniviking").args(&args);
    set_miniviking_binary_env(&mut command);
    prepend_pythonpath(&mut command, &source_root.join("src"));

    #[cfg(unix)]
    command.arg0(process_title(&args));

    run_python(&mut command)
}

fn command_requires_bootstrap(args: &[OsString]) -> bool {
    if args.iter().any(|arg| arg == "-h" || arg == "--help") {
        return false;
    }

    let Some(first) = args.first().and_then(|arg| arg.to_str()) else {
        return false;
    };

    !matches!(
        first,
        "config"
            | "openviking-config"
            | "test"
            | "start"
            | "stop"
            | "restart"
            | "status"
            | "uninstall"
    )
}

fn process_role(args: &[OsString]) -> Option<&'static str> {
    match args.first().and_then(|arg| arg.to_str()) {
        Some("serve") => Some(SERVER_ROLE),
        Some(command) if command == SERVER_ROLE => Some(SERVER_ROLE),
        Some(command) if command == LLM_ROLE => Some(LLM_ROLE),
        Some(command) if command == EMBED_ROLE => Some(EMBED_ROLE),
        _ => None,
    }
}

fn process_title(args: &[OsString]) -> OsString {
    OsString::from(process_role(args).unwrap_or("miniviking"))
}

fn role_python_runner(runner: OsString, role: Option<&'static str>) -> OsString {
    let Some(role) = role else {
        return runner;
    };
    let Some(parent) = Path::new(runner.as_os_str()).parent() else {
        return runner;
    };
    let named_runner = parent.join(role);
    if named_runner.is_file() {
        named_runner.into_os_string()
    } else {
        runner
    }
}

fn set_miniviking_binary_env(command: &mut Command) {
    if env::var_os("MINIVIKING_BINARY").is_some() {
        return;
    }
    if let Ok(executable) = env::current_exe() {
        command.env("MINIVIKING_BINARY", executable);
    }
}

fn python_command() -> OsString {
    if let Some(path) = env::var_os("MINIVIKING_PYTHON") {
        return path;
    }
    if let Some(path) = DEFAULT_PYTHON {
        return OsString::from(path);
    }

    for candidate in [
        "/opt/homebrew/opt/python@3.13/bin/python3.13",
        "/usr/local/opt/python@3.13/bin/python3.13",
    ] {
        if Path::new(candidate).exists() {
            return OsString::from(candidate);
        }
    }

    OsString::from("python3")
}

fn python_source_root() -> Result<PathBuf, String> {
    if let Some(path) = env::var_os("MINIVIKING_PYTHON_SOURCE") {
        return validate_source_root(PathBuf::from(path));
    }
    if let Some(path) = DEFAULT_SOURCE {
        return validate_source_root(PathBuf::from(path));
    }

    if let Ok(exe) = env::current_exe() {
        if let Some(prefix) = exe.parent().and_then(Path::parent) {
            let candidate = prefix.join("libexec").join("python");
            if source_root_exists(&candidate) {
                return Ok(candidate);
            }
        }
    }

    if let Some(manifest_dir) = option_env!("CARGO_MANIFEST_DIR") {
        return validate_source_root(PathBuf::from(manifest_dir));
    }

    Err("could not locate bundled Python source; set MINIVIKING_PYTHON_SOURCE".to_string())
}

fn validate_source_root(path: PathBuf) -> Result<PathBuf, String> {
    if source_root_exists(&path) {
        Ok(path)
    } else {
        Err(format!(
            "Python source root is invalid: {}",
            path.to_string_lossy()
        ))
    }
}

fn source_root_exists(path: &Path) -> bool {
    path.join("pyproject.toml").is_file()
        && path
            .join("src")
            .join("miniviking")
            .join("__init__.py")
            .is_file()
}

fn ensure_runtime(python: &OsStr, source_root: &Path) -> Result<PathBuf, String> {
    let runtime_dir = runtime_dir()?;
    let venv_dir = runtime_dir.join("venv");
    let venv_python = venv_dir.join("bin").join("python");
    let marker = runtime_dir.join("source-root");
    let source_marker = source_root.to_string_lossy().to_string();

    if venv_python.is_file() && marker_contents(&marker).as_deref() == Some(source_marker.as_str())
    {
        ensure_role_python_links(&venv_python)?;
        return Ok(venv_python);
    }

    fs::create_dir_all(&runtime_dir).map_err(|error| {
        format!(
            "failed to create runtime directory {}: {error}",
            runtime_dir.to_string_lossy()
        )
    })?;

    eprintln!(
        "miniviking: preparing Python runtime at {}",
        venv_dir.to_string_lossy()
    );

    if !venv_python.is_file() {
        run_checked(Command::new(python).arg("-m").arg("venv").arg(&venv_dir))?;
    }
    run_checked(
        Command::new(&venv_python)
            .arg("-m")
            .arg("pip")
            .arg("install")
            .arg("--upgrade")
            .arg("pip"),
    )?;
    run_checked(
        Command::new(&venv_python)
            .arg("-m")
            .arg("pip")
            .arg("install")
            .arg("--upgrade")
            .arg(source_root),
    )?;

    fs::write(&marker, source_marker).map_err(|error| {
        format!(
            "failed to write runtime marker {}: {error}",
            marker.to_string_lossy()
        )
    })?;

    ensure_role_python_links(&venv_python)?;
    Ok(venv_python)
}

#[cfg(unix)]
fn ensure_role_python_links(venv_python: &Path) -> Result<(), String> {
    let Some(bin_dir) = venv_python.parent() else {
        return Err(format!(
            "runtime Python path has no parent directory: {}",
            venv_python.to_string_lossy()
        ));
    };
    let Some(target_name) = venv_python.file_name() else {
        return Err(format!(
            "runtime Python path has no file name: {}",
            venv_python.to_string_lossy()
        ));
    };
    let target = Path::new(target_name);

    for role in ROLE_COMMANDS {
        let link = bin_dir.join(role);
        match fs::symlink_metadata(&link) {
            Ok(metadata) if metadata.file_type().is_symlink() => {
                let current = fs::read_link(&link).map_err(|error| {
                    format!(
                        "failed to read runtime process-name helper {}: {error}",
                        link.to_string_lossy()
                    )
                })?;
                if current == target || current == venv_python {
                    continue;
                }
                fs::remove_file(&link).map_err(|error| {
                    format!(
                        "failed to replace runtime process-name helper {}: {error}",
                        link.to_string_lossy()
                    )
                })?;
            }
            Ok(_) => {
                return Err(format!(
                    "runtime process-name helper already exists and is not a symlink: {}",
                    link.to_string_lossy()
                ));
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => {
                return Err(format!(
                    "failed to inspect runtime process-name helper {}: {error}",
                    link.to_string_lossy()
                ));
            }
        }

        std::os::unix::fs::symlink(target, &link).map_err(|error| {
            format!(
                "failed to create runtime process-name helper {}: {error}",
                link.to_string_lossy()
            )
        })?;
    }

    Ok(())
}

#[cfg(not(unix))]
fn ensure_role_python_links(_venv_python: &Path) -> Result<(), String> {
    Ok(())
}

fn runtime_dir() -> Result<PathBuf, String> {
    if let Some(path) = env::var_os("MINIVIKING_RUNTIME_DIR") {
        return Ok(PathBuf::from(path));
    }
    let Some(home) = env::var_os("HOME") else {
        return Err("HOME is not set; set MINIVIKING_RUNTIME_DIR".to_string());
    };
    Ok(PathBuf::from(home).join(".miniviking").join("runtime"))
}

fn marker_contents(path: &Path) -> Option<String> {
    fs::read_to_string(path).ok()
}

fn run_checked(command: &mut Command) -> Result<(), String> {
    let debug = format!("{command:?}");
    let status = command
        .status()
        .map_err(|error| format!("failed to start {debug}: {error}"))?;
    if status.success() {
        Ok(())
    } else {
        Err(format!("{debug} exited with {status}"))
    }
}

#[cfg(unix)]
fn run_python(command: &mut Command) -> i32 {
    let error = command.exec();
    eprintln!("miniviking: failed to run Python runtime: {error}");
    1
}

#[cfg(not(unix))]
fn run_python(command: &mut Command) -> i32 {
    match command.status() {
        Ok(status) => exit_code(status),
        Err(error) => {
            eprintln!("miniviking: failed to run Python runtime: {error}");
            1
        }
    }
}

fn prepend_pythonpath(command: &mut Command, path: &Path) {
    let mut paths = vec![path.to_path_buf()];
    if let Some(existing) = env::var_os("PYTHONPATH") {
        paths.extend(env::split_paths(&existing));
    }
    if let Ok(value) = env::join_paths(paths) {
        command.env("PYTHONPATH", value);
    }
}

#[cfg(not(unix))]
fn exit_code(status: ExitStatus) -> i32 {
    status.code().unwrap_or(1)
}

#[cfg(test)]
mod tests {
    use std::ffi::OsString;
    use std::fs;
    use std::path::PathBuf;
    use std::time::{SystemTime, UNIX_EPOCH};

    use super::{
        command_requires_bootstrap, ensure_role_python_links, process_title, role_python_runner,
        EMBED_ROLE, LLM_ROLE, ROLE_COMMANDS, SERVER_ROLE,
    };

    fn args(values: &[&str]) -> Vec<OsString> {
        values.iter().map(OsString::from).collect()
    }

    #[test]
    fn help_does_not_require_bootstrap() {
        assert!(!command_requires_bootstrap(&args(&["--help"])));
        assert!(!command_requires_bootstrap(&args(&["install", "--help"])));
    }

    #[test]
    fn passive_commands_do_not_require_bootstrap() {
        for command in [
            "config",
            "openviking-config",
            "test",
            "start",
            "stop",
            "restart",
            "status",
            "uninstall",
        ] {
            assert!(!command_requires_bootstrap(&args(&[command])));
        }
    }

    #[test]
    fn model_runtime_commands_require_bootstrap() {
        for command in ["install", "serve", SERVER_ROLE, LLM_ROLE, EMBED_ROLE] {
            assert!(command_requires_bootstrap(&args(&[command])));
        }
    }

    #[test]
    fn role_commands_use_role_process_titles() {
        assert_eq!(
            process_title(&args(&["serve"])),
            OsString::from(SERVER_ROLE)
        );
        assert_eq!(
            process_title(&args(&[SERVER_ROLE])),
            OsString::from(SERVER_ROLE)
        );
        assert_eq!(process_title(&args(&[LLM_ROLE])), OsString::from(LLM_ROLE));
        assert_eq!(
            process_title(&args(&[EMBED_ROLE])),
            OsString::from(EMBED_ROLE)
        );
    }

    #[test]
    fn non_role_commands_use_default_process_title() {
        assert_eq!(process_title(&args(&[])), OsString::from("miniviking"));
        assert_eq!(
            process_title(&args(&["install"])),
            OsString::from("miniviking")
        );
        assert_eq!(
            process_title(&args(&["config"])),
            OsString::from("miniviking")
        );
    }

    #[cfg(unix)]
    #[test]
    fn runtime_role_python_links_are_created() {
        let root = unique_temp_dir("miniviking-role-links");
        let bin = root.join("bin");
        fs::create_dir_all(&bin).unwrap();
        let python = bin.join("python");
        fs::write(&python, "").unwrap();

        ensure_role_python_links(&python).unwrap();

        for role in ROLE_COMMANDS {
            assert_eq!(
                fs::read_link(bin.join(role)).unwrap(),
                PathBuf::from("python")
            );
        }

        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn role_python_runner_uses_named_runtime_link_when_present() {
        let root = unique_temp_dir("miniviking-role-runner");
        let bin = root.join("bin");
        fs::create_dir_all(&bin).unwrap();
        let python = bin.join("python");
        fs::write(&python, "").unwrap();
        ensure_role_python_links(&python).unwrap();

        let runner = role_python_runner(python.into_os_string(), Some(LLM_ROLE));

        assert_eq!(PathBuf::from(runner), bin.join(LLM_ROLE));

        fs::remove_dir_all(root).unwrap();
    }

    fn unique_temp_dir(prefix: &str) -> PathBuf {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        std::env::temp_dir().join(format!("{prefix}-{}-{nanos}", std::process::id()))
    }
}
