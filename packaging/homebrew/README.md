# Homebrew Formula

`Formula/miniviking.rb` installs from source:

- `brew install le0-VV/miniviking/miniviking` builds the Rust launcher from source and installs the Python package source under `libexec`.
- The formula does not install prebuilt binaries and does not create a Python virtualenv during the Homebrew build.

User install command:

```sh
brew tap le0-VV/miniviking https://github.com/le0-VV/miniviking
brew install le0-VV/miniviking/miniviking
```

The installed `miniviking` binary is a Rust launcher. It prepares the Python/MLX
runtime under `~/.miniviking/runtime` when `miniviking install` or the server is
first run, so dependency and model downloads happen outside the Homebrew formula
build.

On 8 GB machines, `miniviking install` defaults to embedding-only mode and does
not download a local LLM unless the user passes `--mode both` or `--mode llm`.

Before moving the formula to a tagged source release:

1. Create and push the source tag:

   ```text
   v0.1.0
   ```

2. Replace the temporary `branch: "main"` source URL with a tagged source archive:

   ```text
   https://github.com/le0-VV/miniviking/archive/refs/tags/v0.1.0.tar.gz
   ```

3. Add the source archive SHA to `Formula/miniviking.rb`.

4. Verify locally:

   ```sh
   ruby -c Formula/miniviking.rb
   brew audit --strict --online le0-VV/miniviking/miniviking
   brew install le0-VV/miniviking/miniviking
   miniviking --help
   ```
