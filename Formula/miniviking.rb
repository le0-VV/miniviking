# frozen_string_literal: true

class Miniviking < Formula
  desc "Tiny local MLX runtime for OpenViking"
  homepage "https://github.com/le0-VV/miniviking"
  url "https://github.com/le0-VV/miniviking/releases/download/v0.1.0/miniviking-0.1.0-aarch64-apple-darwin.tar.gz"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  license "MIT"

  head do
    url "https://github.com/le0-VV/miniviking.git", branch: "main"
    depends_on "python@3.13"
    depends_on "uv" => :build
  end

  depends_on arch: :arm64
  depends_on :macos

  def install
    if build.head?
      ENV["UV_LINK_MODE"] = "copy"
      ENV["UV_PYTHON_DOWNLOADS"] = "never"

      system Formula["python@3.13"].opt_bin/"python3.13", "-m", "venv", "--without-pip", libexec
      system "uv", "pip", "install", "--python", libexec/"bin/python", "--compile-bytecode", "."
      bin.install_symlink libexec/"bin/miniviking"
    else
      bin.install "miniviking"
    end
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

      Miniviking requires Apple Silicon because MLX is Apple Silicon only.
    EOS
  end

  test do
    assert_match "usage:", shell_output("#{bin}/miniviking --help")
  end
end
