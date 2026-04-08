from datetime import datetime
import os
import requests

GRAPHQL_URL = "https://api.github.com/graphql"

YTD_START = f"{datetime.now().year}-01-01T00:00:00Z"
YTD_NOW = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

STATS_QUERY = f"""
query userInfo($login: String!) {{
  user(login: $login) {{
    name
    login
    commits: contributionsCollection(from: "{YTD_START}", to: "{YTD_NOW}") {{
      totalCommitContributions
    }}
    repositoriesContributedTo(
      first: 10
      contributionTypes: [COMMIT, PULL_REQUEST]
      orderBy: {{ direction: DESC, field: CREATED_AT }}
    ) {{
      totalCount
      nodes {{
        nameWithOwner
        description
        stargazers {{
          totalCount
        }}
      }}
    }}
    pullRequests(first: 1) {{
      totalCount
    }}
    mergedPullRequests: pullRequests(states: MERGED) {{
      totalCount
    }}
    openIssues: issues(states: OPEN) {{
      totalCount
    }}
    closedIssues: issues(states: CLOSED) {{
      totalCount
    }}
    followers {{
      totalCount
    }}
    repositories(first: 100, ownerAffiliations: OWNER) {{
      totalCount
      nodes {{
        name
        stargazers {{
          totalCount
        }}
      }}
    }}
  }}
}}
"""

LANGUAGES_QUERY = """
query userInfo($login: String!) {
  user(login: $login) {
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100) {
      nodes {
        name
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges {
            size
            node {
              color
              name
            }
          }
        }
      }
    }
  }
}
"""


def graphql_request(query: str, username: str, token: str):
    headers = {
        "Authorization": f"token {token}",
        "Content-Type": "application/json",
    }
    payload = {"query": query, "variables": {"login": username}}
    response = requests.post(GRAPHQL_URL, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()


def get_stats(username: str, token: str):
    data = graphql_request(STATS_QUERY, username, token)["data"]["user"]

    stars = sum(r["stargazers"]["totalCount"] for r in data["repositories"]["nodes"])

    contributed = []
    for repo in data["repositoriesContributedTo"]["nodes"]:
        name = repo["nameWithOwner"]
        if name.lower().startswith(username.lower() + "/"):
            continue
        contributed.append({
            "name": name,
            "stars": repo["stargazers"]["totalCount"],
        })

    return {
        "name": data["name"] or data["login"],
        "stars": stars,
        "commits": data["commits"]["totalCommitContributions"],
        "prs": data["pullRequests"]["totalCount"],
        "merged_prs": data["mergedPullRequests"]["totalCount"],
        "issues": data["openIssues"]["totalCount"] + data["closedIssues"]["totalCount"],
        "followers": data["followers"]["totalCount"],
        "repos": data["repositories"]["totalCount"],
        "contributed": contributed,
    }


def get_languages(username: str, token: str):
    data = graphql_request(LANGUAGES_QUERY, username, token)
    nodes = data["data"]["user"]["repositories"]["nodes"]

    languages = {}
    for repo in nodes:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            size = edge["size"]
            languages[name] = languages.get(name, 0) + size

    return dict(sorted(languages.items(), key=lambda x: x[1], reverse=True))


def bucket_languages(languages: dict, threshold: float = 1.0):
    """Keep languages above threshold%, group the rest as 'other'."""
    total = sum(languages.values())
    if total == 0:
        return {}

    result = {}
    other = 0
    for lang, size in languages.items():
        if (size / total) * 100 >= threshold:
            result[lang] = size
        else:
            other += size

    if other > 0:
        result["other"] = other

    return result


def percent_bar(percent: float, width: int = 20):
    percent = max(0, min(100, percent))
    filled = round((percent / 100) * width)
    empty = width - filled
    return f"{'█' * filled}{'░' * empty}"


def row(label: str, value, width: int = 16):
    return f"  {label:<{width}}  {value}"


def divider(title: str, total_width: int = 58):
    side = total_width - len(title) - 4
    return f"  -- {title} {'─' * side}"


def generate_readme(username: str, token: str, path: str = "README.md"):
    stats = get_stats(username, token)
    raw_languages = get_languages(username, token)
    languages = bucket_languages(raw_languages, threshold=1.0)

    total_lang_size = sum(languages.values())
    now = datetime.now().strftime("%Y-%m-%d %H:%M UTC")

    lines = ["```"]

    #header
    #lines += [
    #    f"  ┌─────────────────────────────────────────────────────────┐",
    #    f"  │  ~ {stats['name']:<53}│",
    #    f"  │  $ github.com/{username:<43}│",
    #    f"  └─────────────────────────────────────────────────────────┘",
    #    "",
    #]

    # stats
    lines += [
        divider("stats"),
        "",
        row("> stars",         stats["stars"]),
        row("> commits (ytd)",   stats["commits"]),
        row("> pull requests", f"{stats['prs']}  ({stats['merged_prs']} merged)"),
        "",
    ]

    #  languages
    lines += [divider("languages"), ""]
    for lang, size in languages.items():
        percent = (size / total_lang_size) * 100 if total_lang_size > 0 else 0
        bar = percent_bar(percent)
        lines.append(f"  {lang:<14}  {bar}  {percent:4.1f}%")
    lines.append("")

    # contributed to
    #if stats["contributed"]:
    #    lines += [divider("contributed to"), ""]
    #    for repo in stats["contributed"][:6]:
    #        star_str = f"  ★ {repo['stars']}" if repo["stars"] else ""
    #        lines.append(f"  > {repo['name']}{star_str}")
    #    lines.append("") 
    #lines.append("")

    lines.append("```")

    # footer
    #lines += [
    #    f"<small><small> > Last update:  {now} </small></small>",
    #]

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    # print(f"README.md generated for @{username}")


if __name__ == "__main__":
    username = "manutonial"
    token = os.getenv("GITHUB_TOKEN", "")

    if not token:
        raise ValueError("GITHUB_TOKEN environment variable is not set.")

    generate_readme(username, token)
