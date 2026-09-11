import readline from 'node:readline';
import { pathToFileURL } from 'node:url';
const { PGlite } = await import(pathToFileURL(process.env.SYLVEX_PGLITE_MODULE).href);
const db = new PGlite();
for await (const line of readline.createInterface({input:process.stdin})) {
 try {
  const {sql,params} = JSON.parse(line);
  const result = await db.query(sql,params || []);
  // Build rows positionally from result.fields rather than Object.values(row):
  // an unaliased duplicate expression column (e.g. two EXTRACT(...) calls)
  // produces two same-named keys on the row object, and Object.values would
  // silently collapse them to one - a real cursor never has this problem
  // since psycopg2 rows are positional tuples, not name-keyed objects.
  const fieldNames = result.fields.map(f=>f.name);
  const rows = result.rows.map(row=>fieldNames.map(name=>row[name]));
  process.stdout.write(JSON.stringify({rows,count:result.affectedRows || 0})+'\n');
 } catch (e) { process.stdout.write(JSON.stringify({error:String(e.message)})+'\n'); }
}
await db.close();
