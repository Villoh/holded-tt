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
        holded-tt = pkgs.python3Packages.buildPythonApplication {
          pname = "holded-tt";
          # One source of truth for the version: pyproject.toml.
          version = (builtins.fromTOML (builtins.readFile ./pyproject.toml)).project.version;
          pyproject = true;
          src = ./.;
          build-system = [ pkgs.python3Packages.hatchling ];
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
