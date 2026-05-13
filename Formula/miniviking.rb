# frozen_string_literal: true

class Miniviking < Formula
  desc "Tiny local MLX runtime for OpenViking"
  homepage "https://github.com/REPLACE_WITH_OWNER/miniviking"
  url "https://github.com/REPLACE_WITH_OWNER/miniviking/releases/download/v0.1.0/miniviking-0.1.0-aarch64-apple-darwin.tar.gz"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  license "MIT"

  depends_on arch: :arm64
  depends_on :macos

  def install
    bin.install "miniviking"
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
