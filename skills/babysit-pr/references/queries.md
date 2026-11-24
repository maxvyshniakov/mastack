# Queries

`OWNER`, `REPO` and `N` are the base repository and the PR number.

Checks, with links to the failing runs:

```sh
gh pr checks N --repo OWNER/REPO
gh run view RUN_ID --repo OWNER/REPO --log-failed
```

Review threads with their resolution state; the REST API has comments but not
threads:

```sh
gh api graphql -F owner=OWNER -F repo=REPO -F n=N -f query='
query($owner:String!,$repo:String!,$n:Int!){repository(owner:$owner,name:$repo){pullRequest(number:$n){
  reviewThreads(first:100){nodes{id isResolved isOutdated path line
    comments(first:20){nodes{databaseId author{login} body createdAt}}}}}}}' \
  --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved|not)'
```

PR-level comments, labels and review state:

```sh
gh pr view N --repo OWNER/REPO --json labels,reviewDecision,comments,reviews,headRefOid
```

Reply in a review thread (the id is a comment's `databaseId`):

```sh
gh api -X POST repos/OWNER/REPO/pulls/N/comments/COMMENT_ID/replies -f body='...'
```

A bot that edits one summary comment per review: take the comment with the
newest `updated_at` from `gh api repos/OWNER/REPO/issues/N/comments`.
