use std::env;
use std::ffi::{c_char, c_int, CStr, CString, OsStr, OsString};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

const DEFAULT_PYTHON: Option<&str> = option_env!("MINIVIKING_DEFAULT_PYTHON");
const DEFAULT_SOURCE: Option<&str> = option_env!("MINIVIKING_DEFAULT_SOURCE");
pub const SERVER_ROLE: &str = "miniviking-server";
pub const LLM_ROLE: &str = "miniviking-llm";
pub const EMBED_ROLE: &str = "miniviking-embed";

const EMBEDDED_ENTRYPOINT: &str = r#"
import json
import os
import sys
import traceback

sys.argv = json.loads(os.environ["MINIVIKING_EMBEDDED_ARGV"])
sys.executable = os.environ["MINIVIKING_EMBEDDED_EXECUTABLE"]

try:
    from miniviking.cli import main as _main
    _main(sys.argv[1:])
except SystemExit as _exc:
    _code = _exc.code
    if _code is None:
        _code = 0
    elif not isinstance(_code, int):
        print(_code, file=sys.stderr)
        _code = 1
except BaseException:
    traceback.print_exc()
    _code = 1
else:
    _code = 0

sys.stdout.flush()
sys.stderr.flush()
os._exit(_code)
"#;

extern "C" {
    fn Py_Initialize();
    fn PyRun_SimpleString(command: *const c_char) -> c_int;
    fn Py_GetVersion() -> *const c_char;
}

pub fn run_cli() -> i32 {
    run(None)
}

pub fn run_role(role: &'static str) -> i32 {
    run(Some(role))
}

fn run(default_role: Option<&'static str>) -> i32 {
    let args = runtime_args(default_role);
    let source_root = match python_source_root() {
        Ok(path) => path,
        Err(error) => {
            eprintln!("miniviking: {error}");
            return 1;
        }
    };
    let python = python_command();
    let site_packages = if command_requires_bootstrap(&args) {
        match ensure_runtime(&python, &source_root) {
            Ok(path) => match runtime_site_packages(&path) {
                Ok(site_packages) => Some(site_packages),
                Err(error) => {
                    eprintln!("miniviking: {error}");
                    return 1;
                }
            },
            Err(error) => {
                eprintln!("miniviking: {error}");
                return 1;
            }
        }
    } else {
        None
    };

    if let Err(error) = prepare_python_environment(&args, &source_root, site_packages.as_deref()) {
        eprintln!("miniviking: {error}");
        return 1;
    }

    run_embedded_python()
}

fn runtime_args(default_role: Option<&'static str>) -> Vec<OsString> {
    let mut args: Vec<OsString> = env::args_os().skip(1).collect();
    if let Some(role) = default_role {
        if args.first().and_then(|arg| arg.to_str()) != Some(role) {
            args.insert(0, OsString::from(role));
        }
    }
    args
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

fn runtime_site_packages(venv_python: &Path) -> Result<PathBuf, String> {
    let output = Command::new(venv_python)
        .arg("-c")
        .arg("import sysconfig; print(sysconfig.get_paths()['purelib'])")
        .output()
        .map_err(|error| {
            format!(
                "failed to inspect runtime site-packages using {}: {error}",
                venv_python.to_string_lossy()
            )
        })?;
    if !output.status.success() {
        return Err(format!(
            "{} failed while inspecting runtime site-packages",
            venv_python.to_string_lossy()
        ));
    }
    let stdout = String::from_utf8(output.stdout)
        .map_err(|error| format!("runtime site-packages path is not utf-8: {error}"))?;
    let path = stdout.trim();
    if path.is_empty() {
        return Err("runtime site-packages path is empty".to_string());
    }
    Ok(PathBuf::from(path))
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

fn prepare_python_environment(
    args: &[OsString],
    source_root: &Path,
    site_packages: Option<&Path>,
) -> Result<(), String> {
    env::set_var("MINIVIKING_EMBEDDED_ARGV", embedded_argv_json(args)?);
    let executable = env::current_exe().unwrap_or_else(|_| PathBuf::from("miniviking"));
    env::set_var("MINIVIKING_EMBEDDED_EXECUTABLE", executable);

    let mut paths = vec![source_root.join("src")];
    if let Some(site_packages) = site_packages {
        paths.push(site_packages.to_path_buf());
    }
    if let Some(existing) = env::var_os("PYTHONPATH") {
        paths.extend(env::split_paths(&existing));
    }
    let value =
        env::join_paths(paths).map_err(|error| format!("failed to build PYTHONPATH: {error}"))?;
    env::set_var("PYTHONPATH", value);
    Ok(())
}

fn embedded_argv_json(args: &[OsString]) -> Result<String, String> {
    let mut values = vec!["miniviking".to_string()];
    for arg in args {
        let Some(value) = arg.to_str() else {
            return Err("command arguments must be valid UTF-8".to_string());
        };
        values.push(value.to_string());
    }

    let mut json = String::from("[");
    for (index, value) in values.iter().enumerate() {
        if index > 0 {
            json.push(',');
        }
        json.push('"');
        push_json_string_content(&mut json, value);
        json.push('"');
    }
    json.push(']');
    Ok(json)
}

fn push_json_string_content(target: &mut String, value: &str) {
    for character in value.chars() {
        match character {
            '"' => target.push_str("\\\""),
            '\\' => target.push_str("\\\\"),
            '\u{08}' => target.push_str("\\b"),
            '\u{0c}' => target.push_str("\\f"),
            '\n' => target.push_str("\\n"),
            '\r' => target.push_str("\\r"),
            '\t' => target.push_str("\\t"),
            character if character <= '\u{1f}' => {
                target.push_str(&format!("\\u{:04x}", character as u32));
            }
            character => target.push(character),
        }
    }
}

fn run_embedded_python() -> i32 {
    let entrypoint = CString::new(EMBEDDED_ENTRYPOINT).expect("embedded Python contains no NUL");
    unsafe {
        Py_Initialize();
        let result = PyRun_SimpleString(entrypoint.as_ptr());
        if result == 0 {
            return 0;
        }
        let version = CStr::from_ptr(Py_GetVersion()).to_string_lossy();
        eprintln!("miniviking: embedded Python {version} failed before Miniviking could exit");
        1
    }
}

#[cfg(test)]
mod tests {
    use super::{
        command_requires_bootstrap, embedded_argv_json, EMBED_ROLE, LLM_ROLE, SERVER_ROLE,
    };
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
        for command in ["install", "serve", SERVER_ROLE, LLM_ROLE, EMBED_ROLE] {
            assert!(command_requires_bootstrap(&args(&[command])));
        }
    }

    #[test]
    fn embedded_argv_escapes_json_strings() {
        assert_eq!(
            embedded_argv_json(&args(&["config", "quote\"slash\\tab\t"])).unwrap(),
            "[\"miniviking\",\"config\",\"quote\\\"slash\\\\tab\\t\"]"
        );
    }

    #[test]
    fn role_runtime_args_prepend_role_command() {
        let original_args = runtime_args_for_test(Some(LLM_ROLE), &["--config", "config.json"]);

        assert_eq!(original_args, args(&[LLM_ROLE, "--config", "config.json"]));
    }

    #[test]
    fn role_runtime_args_do_not_duplicate_role_command() {
        let original_args =
            runtime_args_for_test(Some(EMBED_ROLE), &[EMBED_ROLE, "--config", "config.json"]);

        assert_eq!(
            original_args,
            args(&[EMBED_ROLE, "--config", "config.json"])
        );
    }

    fn runtime_args_for_test(default_role: Option<&'static str>, values: &[&str]) -> Vec<OsString> {
        let mut args = values.iter().map(OsString::from).collect::<Vec<_>>();
        if let Some(role) = default_role {
            if args.first().and_then(|arg| arg.to_str()) != Some(role) {
                args.insert(0, OsString::from(role));
            }
        }
        args
    }
}
