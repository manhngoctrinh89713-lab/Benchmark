# Derived from modelcontextprotocol/servers Git MCP (MIT).
import git
DEFAULT_CONTEXT_LINES = 3


def _git_text(repo: git.Repo, command: str, *args: str) -> str:
    """Run `git <command> <args>` for a tool that hands git's output to the client.

    Two things about that output are fixed here, for git_status and the three
    diff tools alike:

    - Paths (#5129). Under git's default `core.quotepath=true`, every byte of a
      path at or above 0x80 prints as an octal escape (`"\\346\\227\\245.txt"`),
      a name the client cannot pass back to git_add. `-c core.quotepath=false`
      prints such names as written, for this one command only: nothing is
      written to the repository's config. Git still C-quotes a name holding a
      control character (a tab, say) or a double quote or backslash; the flag
      governs only the high-bit bytes.
    - Content (#5193). GitPython decodes output with surrogateescape, so a
      non-UTF-8 file (Latin-1, say) leaves lone surrogates that cannot be
      serialized as UTF-8. Take the bytes and replace what does not decode
      with U+FFFD, as git_show does.

    The `-c` has to come before the subcommand, so it goes through
    `repo.git(c=...)`; `repo.git.status(c=...)` would put it after and fail.
    That call sets the option on the shared `repo.git` until its next command
    runs, which is the one made here.
    """
    output = getattr(repo.git(c="core.quotepath=false"), command)(
        *args, stdout_as_string=False
    )
    return output.decode("utf-8", errors="replace")


def git_status(repo: git.Repo) -> str:
    return _git_text(repo, "status")


def git_diff_unstaged(
    repo: git.Repo, context_lines: int = DEFAULT_CONTEXT_LINES
) -> str:
    return _git_text(repo, "diff", "--no-ext-diff", "--no-textconv", f"--unified={context_lines}")


def git_diff_staged(repo: git.Repo, context_lines: int = DEFAULT_CONTEXT_LINES) -> str:
    return _git_text(repo, "diff", "--no-ext-diff", "--no-textconv", f"--unified={context_lines}", "--cached")
