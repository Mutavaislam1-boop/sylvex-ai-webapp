import readline from 'node:readline';
import { pathToFileURL } from 'node:url';
const { PGlite } = await import(pathToFileURL(process.env.SYLVEX_PGLITE_MODULE).href);
const db = new PGlite();
for await (const line of readline.createInterface({input:process.stdin})) {
 try {
  const {sql,params} = JSON.parse(line);
  const result = await db.query(sql,params || []);
  process.stdout.write(JSON.stringify({rows:result.rows.map(row=>Object.values(row)),count:result.affectedRows || 0})+'\n');
 } catch (e) { process.stdout.write(JSON.stringify({error:String(e.message)})+'\n'); }
}
await db.close();
