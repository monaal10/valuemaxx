#!/usr/bin/env node
/**
 * The `valuemaxx` executable (npm `bin`). Thin shim over the onboard CLI so `valuemaxx onboard`
 * works the same as the Python `valuemaxx onboard`.
 */

import { main } from "./onboarding/cli.js";

main()
  .then((code) => process.exit(code))
  .catch((err: unknown) => {
    process.stderr.write(`valuemaxx: ${String(err)}\n`);
    process.exit(1);
  });
