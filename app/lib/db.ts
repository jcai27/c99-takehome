// The Postgres client. Mirrors workflows/lib/db.py's DATABASE_URL pattern --
// same default, same env var, read from the same place docker-compose.yaml
// already wires up for both the containerized worker and this app.

import postgres from "postgres";

const DATABASE_URL =
  process.env.DATABASE_URL ?? "postgres://postgres:postgres@localhost:5432/chp99";

const sql = postgres(DATABASE_URL);

export default sql;
