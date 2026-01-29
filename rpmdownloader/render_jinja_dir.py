#!/usr/bin/env python3
"""
Recursively render all Jinja2 templates in a directory with a single context dictionary.
Each template may use only a subset of the context variables.
"""

import argparse
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


def find_templates(root: Path, extensions: tuple[str, ...]) -> list[Path]:
    """Recursively find all files with given extensions under root."""
    return [
        p for p in root.rglob("*")
        if p.is_file() and p.suffix in extensions
    ]


def render_dir(
    input_dir: Path,
    output_dir: Path,
    context: dict,
    template_extensions: tuple[str, ...] = (".jinja2", ".jinja", ".j2"),
    in_place: bool = False,
) -> list[Path]:
    """
    Render all Jinja templates under input_dir with the given context.
    Writes rendered content to output_dir (or overwrites if in_place=True).
    """
    input_dir = input_dir.resolve()
    if in_place:
        output_dir = input_dir
    else:
        output_dir = output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(input_dir)),
        autoescape=select_autoescape(default=True, default_for_string=True),
    )

    templates = find_templates(input_dir, template_extensions)
    rendered: list[Path] = []

    for template_path in templates:
        rel = template_path.relative_to(input_dir)
        # Output path: same relative path but with .html or strip template extension
        out_path = output_dir / rel
        if not in_place:
            # Default: output as .html (or keep same stem and use .rendered / strip suffix)
            out_path = out_path.with_suffix(".html")

        template_name = str(rel)
        t = env.get_template(template_name)
        content = t.render(**context)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        rendered.append(out_path)

    return rendered


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recursively render Jinja templates in a directory with a shared context."
    )
    parser.add_argument(
        "input_dir",
        type=Path,
        help="Directory containing Jinja templates",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Output directory (default: input_dir/rendered). Ignored if --in-place.",
    )
    parser.add_argument(
        "-c", "--context",
        type=Path,
        required=True,
        help="JSON file with context dictionary for all templates",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite template files with rendered output (use with caution)",
    )
    parser.add_argument(
        "-e", "--extensions",
        nargs="+",
        default=[".jinja2", ".jinja", ".j2"],
        help="Template file extensions to process (default: .jinja2 .jinja .j2)",
    )
    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    if not input_dir.is_dir():
        raise SystemExit(f"Not a directory: {input_dir}")

    context_path = args.context.resolve()
    if not context_path.is_file():
        raise SystemExit(f"Context file not found: {context_path}")
    context = json.loads(context_path.read_text(encoding="utf-8"))

    if not isinstance(context, dict):
        raise SystemExit("Context JSON must be a top-level object (dict).")

    output_dir = args.output or (input_dir / "rendered")
    if args.in_place:
        output_dir = input_dir

    rendered = render_dir(
        input_dir=input_dir,
        output_dir=output_dir,
        context=context,
        template_extensions=tuple(args.extensions),
        in_place=args.in_place,
    )

    for p in rendered:
        print(p)


if __name__ == "__main__":
    main()
