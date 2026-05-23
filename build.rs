use std::env;
use std::process::Command;

fn main() {
    println!("cargo:rerun-if-env-changed=MINIVIKING_PYTHON_CONFIG");

    let python_config =
        env::var("MINIVIKING_PYTHON_CONFIG").unwrap_or_else(|_| "python3.13-config".to_string());
    let output = Command::new(&python_config)
        .args(["--embed", "--ldflags"])
        .output()
        .unwrap_or_else(|error| panic!("failed to run {python_config}: {error}"));

    if !output.status.success() {
        panic!(
            "{python_config} --embed --ldflags exited with {}",
            output.status
        );
    }

    let stdout = String::from_utf8(output.stdout).expect("python config ldflags must be utf-8");
    let mut tokens = stdout.split_whitespace();
    while let Some(token) = tokens.next() {
        if let Some(path) = token.strip_prefix("-L") {
            println!("cargo:rustc-link-search=native={path}");
        } else if let Some(library) = token.strip_prefix("-l") {
            println!("cargo:rustc-link-lib={library}");
        } else if token == "-framework" {
            let Some(framework) = tokens.next() else {
                panic!("{python_config} emitted -framework without a framework name");
            };
            println!("cargo:rustc-link-lib=framework={framework}");
        }
    }
}
