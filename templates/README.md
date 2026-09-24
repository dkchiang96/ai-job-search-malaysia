# Custom Templates

This folder holds user-registered templates (LaTeX, Typst, `.docx`, or any other toolchain with a declared compile command), managed by the `/add-template` command. The framework works out of the box with its stock templates (moderncv for CVs, `cover.cls` for cover letters) — this folder only gets content when you register your own.

## Layout

```
templates/
├── cv/
│   └── <template-name>/
│       ├── template.<ext>  # Profile-agnostic skeleton ([PLACEHOLDER] tokens), e.g. template.tex, template.typ, or template.docx
│       ├── TEMPLATE.md      # Manifest: source extension, compile command, editing method, fonts, page limit, style rules, pitfalls
│       ├── *.cls / *.sty    # Custom class/style files, or Typst packages (if the template needs them)
│       └── fonts/           # Bundled font files (if not using system fonts)
└── cover_letters/
    └── <template-name>/
        └── (same layout)
```

## How it works

- `/add-template` interviews you for the template's instructions (source extension, compile command, fonts, style rules, page limit), stores the files here, and runs a mandatory test compile before registering anything.
- Activating a template adds a managed block to `05-cv-templates.md` or `06-cover-letter-templates.md`, which is what `/apply` reads when drafting and compiling — no other wiring needed.
- `/add-template --list` shows registered templates; `/add-template --use <name>` switches; `/add-template --use default` reverts to the stock templates.

## Two authoring models

LaTeX and Typst templates are filled by **generating fresh source text** into the placeholder skeleton on every application. A `.docx` template is filled the opposite way — Claude **edits the existing document's XML in place**, so formatting can never drift from what you uploaded. This is the mechanism behind the "use my own Word resume" choice `/setup-malaysia` offers: upload a real `.docx` you like, and every future CV is that same document with new content in the same places. See `.claude/skills/job-application-assistant/10-docx-editing.md` for the full recipe. A ready-made placeholder pair ships in `templates/cv/clean-resume/` and `templates/cover_letters/clean-resume/`. `.docx` conversion to PDF needs either Microsoft Word (Windows, via `tools/docx_to_pdf.ps1`) or LibreOffice (`soffice`, cross-platform) installed.

Templates are stored with `[PLACEHOLDER]` tokens instead of personal data, so they are safe to commit and share. For `.docx` templates specifically, your own real resume content stays in `documents/cv/` (already gitignored) — the stored `template.docx` is a placeholder-only structural reference.
