{
  description = "CLI tool for automating time tracking on Holded";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      forAllSystems =
        f:
        nixpkgs.lib.genAttrs [ "x86_64-linux" "aarch64-linux" ] (
          system: f nixpkgs.legacyPackages.${system}
        );
    in
    {
      packages = forAllSystems (pkgs: rec {
        holded-tt = pkgs.python3Packages.buildPythonApplication {
          pname = "holded-tt";
          # The version comes from git tags (hatch-vcs), which a flake source does not have.
          version = "0+g${self.shortRev or self.dirtyShortRev}";
          pyproject = true;
          src = ./.;
          env.SETUPTOOLS_SCM_PRETEND_VERSION = "0+g${self.shortRev or self.dirtyShortRev}";
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
        };
        default = holded-tt;
      });
    };
}
