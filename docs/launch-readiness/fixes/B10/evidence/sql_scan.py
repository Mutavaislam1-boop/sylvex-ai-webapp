import ast, sys, pathlib, json
root = pathlib.Path(sys.argv[1])
files = [p for p in sorted(root.rglob('*.py')) if not any(x in p.parts for x in ('tests','node_modules','.git','scripts','migrations')) and p.name not in ('stress_test.py','provider_limits_diagnostics.py')]
out = []
for f in files:
    src = f.read_text()
    try: tree = ast.parse(src)
    except SyntaxError as e:
        print('SYNTAX', f, e); continue
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ('execute','executemany','mogrify') and node.args:
            a = node.args[0]
            if isinstance(a, ast.Constant): continue
            kind = type(a).__name__
            exprs = []
            if isinstance(a, ast.JoinedStr):
                exprs = [ast.unparse(v.value) for v in a.values if isinstance(v, ast.FormattedValue)]
            else:
                exprs = [ast.unparse(a)]
            out.append({'file': str(f.relative_to(root)), 'line': node.lineno, 'kind': kind, 'exprs': exprs})
for o in out: print(f"{o['file']}:{o['line']} [{o['kind']}] " + ' | '.join(o['exprs']))
print('TOTAL', len(out))
