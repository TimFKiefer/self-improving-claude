def walk_tree(node, visit):
    """Iterative DFS — depth-bounded by the worklist size."""
    worklist = [node]
    while worklist:
        cur = worklist.pop()
        visit(cur)
        worklist.extend(cur.children)
