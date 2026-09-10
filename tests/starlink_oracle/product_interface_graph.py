"""Complete Icarus continuous connectivity, NOT physical or reachability proof.

Uses the reviewed inverse_sealed_events LS multi-suffix/closure approach and
parent audit_v2's typed aliases, operation allowlist and unknown-reference gate.
Procedural variables and RAM are state cuts. Frozen848's omitted-LS proof is
retained as a negative control, not silently repaired in its original archive.
"""
import re

TOKEN = re.compile(r"\b(?:LS?_0x|v0x)[0-9a-f]+(?:_\d+)*\b")
ALLOWED = {"net", "net/2u", "net/2s", "net/s", "arith/sum", "array/port",
           "cmp/eeq", "cmp/eq", "cmp/gt", "cmp/ne", "cmp/nee", "concat", "concat8",
           "functor", "part", "part/v", "reduce/and", "reduce/nor", "reduce/or",
           "reduce/xor", "shift/l", "ufunc/vec4"}


def parse(source, legacy=False):
    graph, definitions, names = {}, set(), {}
    for line in source.splitlines():
        match = re.match(r"(\w+) \.(\S+) (.*);", line)
        if not match:
            continue
        label, operation, body = match.groups()
        definitions.add(label)
        if operation.startswith("net") or label.startswith(("L_", "LS_")):
            if operation not in ALLOWED:
                raise ValueError("UNKNOWN_OPERATION " + operation)
            if operation.startswith("ufunc") and "product.round_and_saturate" not in body:
                raise ValueError("UNREVIEWED_FUNCTION")
            if not legacy or not label.startswith("LS_"):
                token = r"(?:L_0x|v0x)[0-9a-f]+(?:_\d+)?" if legacy else TOKEN
                graph[label] = set(re.findall(token, body))
            if operation.startswith("net"):
                name = re.search(r'"([^\"]*)"', body).group(1)
                names.setdefault(name, []).append(label)
    if not legacy:
        missing = set().union(set(), *graph.values()) - definitions
        if missing:
            raise ValueError("UNRESOLVED_REFERENCES " + repr(sorted(missing)))
    return graph, names


def first_cycle(graph):
    colors, stack = {}, []
    def walk(node):
        if colors.get(node) == 1:
            return stack[stack.index(node):] + [node]
        if colors.get(node) == 2:
            return None
        colors[node] = 1
        stack.append(node)
        for child in sorted(graph.get(node, ())):
            found = walk(child)
            if found:
                return found
        stack.pop()
        colors[node] = 2
        return None
    for node in sorted(graph):
        found = walk(node)
        if found:
            return found
    return None


def ancestors(graph, roots):
    result, pending = set(), list(roots)
    while pending:
        node = pending.pop()
        if node not in result:
            result.add(node)
            pending.extend(graph.get(node, ()))
    return result
