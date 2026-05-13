# Homebrew Formula

`Formula/miniviking.rb` supports two install paths:

- `brew install --HEAD le0-VV/miniviking/miniviking` builds the current `main` branch into a Homebrew-managed Python virtualenv.
- `brew install le0-VV/miniviking/miniviking` installs the Apple Silicon single-binary release tarball after release assets are published.

User install command before the first binary release:

```sh
brew tap le0-VV/miniviking https://github.com/le0-VV/miniviking
brew install --HEAD le0-VV/miniviking/miniviking
```

The HEAD install path intentionally creates its virtualenv with `--without-pip`
and lets `uv` install Miniviking into it. This avoids depending on Homebrew
Python's `ensurepip` bootstrap during formula builds.

Before publishing the tap:

1. Build a single-binary release asset named:

   ```text
   miniviking-0.1.0-aarch64-apple-darwin.tar.gz
   ```

2. The tarball must contain the executable at its top level:

   ```text
   miniviking
   ```

3. Upload the tarball to the GitHub release for `v0.1.0`.

4. Replace the placeholder SHA in `Formula/miniviking.rb`:

   ```text
   0000000000000000000000000000000000000000000000000000000000000000
   ```

5. Verify locally:

   ```sh
   ruby -c Formula/miniviking.rb
   brew audit --strict --online le0-VV/miniviking/miniviking
   brew install --HEAD le0-VV/miniviking/miniviking
   brew install le0-VV/miniviking/miniviking
   miniviking --help
   ```

User install command once the binary release is published:

```sh
brew tap le0-VV/miniviking https://github.com/le0-VV/miniviking
brew install le0-VV/miniviking/miniviking
```
