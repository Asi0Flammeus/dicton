# Linux Packaging

This project now includes a first Linux release package path alongside the
existing Python package and installer script.

## Current Release Assets

The Linux release flow produces:

- `dicton-linux-x64.tar.gz` - one-folder frozen bundle
- `dicton_<version>_amd64.deb` - Debian package that installs the bundle under `/opt/dicton`

## Build Locally on Linux

```bash
sudo apt-get update
sudo apt-get install -y portaudio19-dev libportaudio2 xdotool xclip libnotify-bin
python3 -m pip install -e ".[linux,packaging]"
./scripts/build-linux-package.sh
```

## Install the Debian Package

```bash
sudo apt install ./dist/dicton_<version>_amd64.deb
```

This is the practical first step toward one-command Linux installs. It is not
yet a hosted APT repository; it is a release asset that can be installed with
`apt install ./...deb`.
