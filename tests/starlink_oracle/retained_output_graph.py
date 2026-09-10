"""Elaboration only: continuous VVP graph and declared-state inventory.

No synthesis, Boolean reachability, vendor netlist, timing or physical claim.
LS_ and repeated numeric suffix handling follows the reviewed inverse helper
8df2c742; this independent parser also rejects every unresolved continuous node.
Procedural variables are cuts; arrays are conservative whole-vector vertices.
"""

import re


def continuous_graph(vvp: str, *, minimum=100) -> dict:
    graph = {}
    operations = set()
    reference = r"(?:LS?_0x[0-9a-f]+(?:_\d+)*|v0x[0-9a-f]+(?:_\d+)*)"
    for line in vvp.splitlines():
        match = re.match(r"^(LS?_\S+) (\.\S+) (.*);", line)
        if match:
            node, operation, body = match.groups()
            if node in graph:
                raise ValueError("duplicate continuous definition")
            operations.add(operation)
            graph[node] = set(re.findall(reference, body))
        match = re.match(r"^(v\S+) \.net(?:/\S+)? (.*);", line)
        if match:
            node, body = match.groups()
            graph[node] = set(re.findall(reference, body))
    if len(graph) < minimum:
        raise ValueError("missing continuous graph")
    if any(child not in graph for children in graph.values() for child in children if child.startswith("L")):
        raise ValueError("unresolved continuous node")
    visited, pending = set(), set()

    def visit(node, stack):
        if node in pending:
            raise ValueError("combinational cycle: " + " -> ".join(stack[stack.index(node):] + [node]))
        if node in visited or node not in graph:
            return
        pending.add(node)
        for child in sorted(graph[node]):
            visit(child, stack + [node])
        pending.remove(node)
        visited.add(node)

    for node in graph:
        visit(node, [])
    return {"nodes": len(graph), "ls_nodes": sum(n.startswith("LS_") for n in graph),
            "operations": sorted(operations), "cyclic": False}


def state_inventory(vvp: str, prefix: str) -> dict:
    """Declared scalar/packed variable bits; arrays inventoried separately."""
    scopes, rows, arrays = {}, [], []
    current = None
    for line in vvp.splitlines():
        scope = re.match(r'^(S_\S+) \.scope \w+, "([^"]+)".*;', line)
        if scope:
            current, name = scope.groups()
            parent = re.search(r", (S_\S+);$", line)
            scopes[current] = (scopes[parent.group(1)] + "." if parent else "") + name
        var = re.match(r'^v\S+ \.var(?:/\S+)? "([^"]+)", (\d+) (\d+);', line)
        array = re.match(r'^v\S+ \.array "([^"]+)", (\d+) (\d+), (\d+) (\d+);', line)
        path = scopes.get(current, "")
        if not (path == prefix or path.startswith(prefix + ".")) or ".shared_xfft" in path:
            continue
        if var:
            name, left, right = var.groups()
            rows.append({"path": path + "." + name, "bits": abs(int(left)-int(right))+1})
        if array:
            name, left, right, msb, lsb = array.groups()
            arrays.append({"path": path + "." + name,
                           "bits": (abs(int(left)-int(right))+1)*(abs(int(msb)-int(lsb))+1)})
    if not rows:
        raise ValueError("missing state scope")
    return {"variables": rows, "arrays": arrays, "declared_bits": sum(r["bits"] for r in rows)}
