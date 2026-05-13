# frozen_string_literal: true

class Miniviking < Formula
  desc "Tiny local MLX runtime for OpenViking"
  homepage "https://github.com/le0-VV/miniviking"
  url "https://github.com/le0-VV/miniviking.git", branch: "main"
  version "0.1.0"
  license "MIT"

  depends_on "rust" => :build
  depends_on "python@3.13"
  depends_on arch: :arm64
  depends_on :macos

  def install
    python_source = libexec/"python"
    ENV["MINIVIKING_DEFAULT_PYTHON"] = (Formula["python@3.13"].opt_bin/"python3.13").to_s
    ENV["MINIVIKING_DEFAULT_SOURCE"] = python_source.to_s

    system "cargo", "install", "--locked", "--root", prefix, "--path", "."
    python_source.install "pyproject.toml", "README.md", "src"
  end

  service do
    run [opt_bin/"miniviking", "miniviking-server", "--config", etc/"miniviking/config.json"]
    keep_alive true
    log_path var/"log/miniviking.log"
    error_log_path var/"log/miniviking.err.log"
    environment_variables MINIVIKING_CONFIG: etc/"miniviking/config.json"
  end

  def caveats
    <<~EOS
      Create the Miniviking config and eagerly download selected models:
        miniviking install --config #{etc}/miniviking/config.json --skip-launch-agent

      Start the Homebrew service:
        brew services start miniviking

      OpenViking should use:
        api_base = "http://127.0.0.1:8745/v1"
        api_key = "local"

      Homebrew builds the Rust launcher from source. The launcher prepares
      the Python/MLX runtime under ~/.miniviking/runtime when needed.

      Miniviking requires Apple Silicon because MLX is Apple Silicon only.
    EOS
  end

  test do
    assert_match "usage:", shell_output("#{bin}/miniviking --help")
  end
end
