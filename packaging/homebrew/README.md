# Homebrew Formula

`Formula/miniviking.rb` is a binary formula for an Apple Silicon release tarball.

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

4. Replace these placeholders in `Formula/miniviking.rb`:

   ```text
   REPLACE_WITH_OWNER
   0000000000000000000000000000000000000000000000000000000000000000
   ```

5. Verify locally:

   ```sh
   ruby -c Formula/miniviking.rb
   brew audit --strict --online REPLACE_WITH_OWNER/miniviking/miniviking
   brew install REPLACE_WITH_OWNER/miniviking/miniviking
   miniviking --help
   ```

User install command once the tap is published:

```sh
brew tap REPLACE_WITH_OWNER/miniviking
brew install miniviking
```
