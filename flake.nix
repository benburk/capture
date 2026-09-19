{
  description = "Save web pages and PDFs as self-contained archive folders";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-25.11";
    # yt-dlp only: YouTube breaks extraction faster than a release
    # channel updates, and a stale one fails in the worst way -- 403 on
    # every adaptive stream, leaving a video capture holding metadata
    # and no video.
    nixpkgs-unstable.url = "github:nixos/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      nixpkgs-unstable,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        unstable = nixpkgs-unstable.legacyPackages.${system};
        # The nightly, not the release unstable carries: YouTube breaks
        # extraction faster than releases repair it, and the failure is
        # silent-ish -- metadata still resolves while every adaptive
        # stream 403s, leaving a video capture with no video. Pinned to
        # the commit the nightly tag was generated from. The same
        # override lives in dotfiles hosts/common/yt-dlp-nightly.nix;
        # they are separate flakes, so bumping one does not move the
        # other.
        yt-dlp-nightly = unstable.yt-dlp.overridePythonAttrs (old: rec {
          version = "2026.09.16.232951";

          src = pkgs.fetchFromGitHub {
            owner = "yt-dlp";
            repo = "yt-dlp";
            rev = "c7fb478d21e9e59524befbe23f7801bb267fb880";
            hash = "sha256-f98zqG5ov/v6EGZxMqeXSRfKegb+XpEMQD/U5oX7F78=";
          };

          # yt-dlp's CI stamps version.py when cutting a nightly; a plain
          # checkout still claims the last release. Appended, not
          # replaced: nixpkgs' own postPatch hardcodes the deno path that
          # YouTube extraction has needed since 2025.11.12.
          postPatch = old.postPatch + ''
            substituteInPlace yt_dlp/version.py \
              --replace-fail "__version__ = '2026.08.19'" "__version__ = '${version}'" \
              --replace-fail "CHANNEL = 'stable'" "CHANNEL = 'nightly'"
          '';
        });
        # Binaries the pipeline shells out to; wrapped onto PATH so an
        # installed capture works outside the devShell.
        runtime = with pkgs; [
          chromium
          single-file-cli
          pandoc
          dprint
          yt-dlp-nightly
          ffmpeg
          git
          poppler-utils
          curl
          fish
        ];
      in
      {
        packages.default = pkgs.python312Packages.buildPythonApplication {
          pname = "capture";
          version = "0.1.0";
          src = self;
          pyproject = true;
          build-system = [ pkgs.python312Packages.hatchling ];
          makeWrapperArgs = [
            "--prefix PATH : ${pkgs.lib.makeBinPath runtime}"
          ];
          # The fish helper stays package data, invoked by path from
          # pipeline.single_file: `capture` is the one installed command.
        };

        apps.default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/capture";
        };

        devShells.default = pkgs.mkShell {
          # PyPI wheels (torch, numpy for marker-pdf) link against
          # libstdc++ and zlib, which NixOS doesn't expose by default.
          LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
            pkgs.stdenv.cc.cc.lib
            pkgs.zlib
          ];
          # yt-dlp (a python3.13 app) leaks its dependency closure into
          # PYTHONPATH, which poisons the project's python3.12 venv;
          # its own wrapper re-adds what it needs.
          shellHook = ''
            unset PYTHONPATH
          '';
          packages = with pkgs; [
            python312
            uv
            ruff
            pyright
            dprint
            fd
            ripgrep
            nixfmt-rfc-style
            single-file-cli
            chromium
            pandoc
            yt-dlp-nightly
            ffmpeg
            git
            poppler-utils
          ];
        };
      }
    );
}
