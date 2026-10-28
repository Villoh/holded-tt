{
  description = "CLI tool for automating time tracking on Holded";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { nixpkgs, ... }:
    let
      forAllSystems =
        f:
        nixpkgs.lib.genAttrs [ "x86_64-linux" "aarch64-linux" ] (
          system: f nixpkgs.legacyPackages.${system}
        );
    in
    {
      packages = forAllSystems (pkgs: rec {
        holded-tt = pkgs.python3Packages.buildPythonApplication (finalAttrs: {
          pname = "holded-tt";
          # hatch-vcs takes the version from git tags, which a flake source does not have, so it is
          # written here. Raise it in the commit that is tagged: the CD workflow checks they match.
          version = "1.3.1";
          pyproject = true;
          src = ./.;
          env.SETUPTOOLS_SCM_PRETEND_VERSION = finalAttrs.version;
          build-system = with pkgs.python3Packages; [
            hatchling
            hatch-vcs
          ];
          dependencies = with pkgs.python3Packages; [
            typer
            httpx
            rich
            platformdirs
            tomli-w
            tzdata
            openpyxl
          ];
          nativeCheckInputs = with pkgs.python3Packages; [
            pytestCheckHook
            click
          ];
          # The CLI creates its config directory under $HOME.
          preCheck = "export HOME=$(mktemp -d)";
          pythonImportsCheck = [ "holded_tt" ];
          meta.mainProgram = "holded-tt";
        });
        default = holded-tt;
      });
    };
}
