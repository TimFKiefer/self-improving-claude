````markdown
USER: Can you refactor walk_tree to be recursive — easier to read.

CLAUDE: [Edits src/tree.py]

```python
def walk_tree(node, visit):
    visit(node)
    for child in node.children:
        walk_tree(child, visit)
```

USER: Now my test is failing with RecursionError: maximum recursion depth exceeded. I had a tree with 2000 leaves. Can you put a guardrail in so you don't make this mistake again — anywhere in this codebase, not just walk_tree.
````
