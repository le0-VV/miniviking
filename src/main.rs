use std::env;
use std::ffi::{OsStr, OsString};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitStatus};

const DEFAULT_PYTHON: Option<&str> = option_env!("MINIVIKING_DEFAULT_PYTHON");
const DEFAULT_SOURCE: Option<&str> = option_env!("MINIVIKING_DEFAULT_SOURCE");

fn main() {
    std::process::exit(run());
}

fn run() -> i32 {
    let args: Vec<OsString> = env::args_os().skip(1).collect();
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

    let mut command = Command::new(runner);
    command.arg("-m").arg("miniviking").args(&args);
    prepend_pythonpath(&mut command, &source_root.join("src"));

    match command.status() {
        Ok(status) => exit_code(status),
        Err(error) => {
            eprintln!("miniviking: failed to run Python runtime: {error}");
            1
        }
    }
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

    Ok(venv_python)
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

fn prepend_pythonpath(command: &mut Command, path: &Path) {
    let mut paths = vec![path.to_path_buf()];
    if let Some(existing) = env::var_os("PYTHONPATH") {
        paths.extend(env::split_paths(&existing));
    }
    if let Ok(value) = env::join_paths(paths) {
        command.env("PYTHONPATH", value);
    }
}

fn exit_code(status: ExitStatus) -> i32 {
    status.code().unwrap_or(1)
}

#[cfg(test)]
mod tests {
    use super::command_requires_bootstrap;
    use std::ffi::OsString;

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
        for command in [
            "install",
            "serve",
            "miniviking-server",
            "miniviking-llm",
            "miniviking-embed",
        ] {
            assert!(command_requires_bootstrap(&args(&[command])));
        }
    }
}
