# Display available recipes
default:
    just --list --unsorted

alias fmt := format

# Set up a fresh checkout to run
setup:
    uv sync

# Format the code and docs
format:
    just --fmt
    ruff check --select I --fix .
    dprint fmt
    fd -e nix -X nixfmt
    # The trailing `.` is required: with no path, ripgrep reads stdin when
    # stdin is not a TTY and blocks forever instead of searching the tree.
    rg -l '[^\n]\z' --multiline . | xargs -r sed -i -e '$a\\'

# Check formatting and lint without changing files
check:
    just --fmt --check
    dprint check
    @fd -e md --hidden -E .git -X awk '/^[[:space:]]*[|]/ && length($0) > 80 {print FILENAME ":" FNR ": table row is " length($0) " chars (>80)"; bad=1} END {exit bad}'
    ruff check --extend-select I .
    pyright .
    fd -e nix -X nixfmt --check
    ! rg -l '[^\n]\z' --multiline .

# Run the tests
test:
    uv run pytest

# Corpus home: collected content, lives under /vault/media (see media/README.md)
sites_dir := "/vault/media/sites"

# Save a page as faithful HTML archive + clean markdown into the corpus
capture url *flags:
    uv run python -m capture -o '{{ sites_dir }}' {{ flags }} '{{ url }}'
