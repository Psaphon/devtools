# Retrofitting `.shellcheckrc` in existing repos

Projects scaffolded after this feature ship with a repo-root `.shellcheckrc` that enables
`external-sources` so shellcheck honours `# shellcheck source=` directives — matching what CI runs.

For repos created before this feature, add it with one command:

```sh
printf 'external-sources=true\nsource-path=SCRIPTDIR\n' > .shellcheckrc
```

Then commit and push. CI's shellcheck job will pick it up automatically on the next run.
