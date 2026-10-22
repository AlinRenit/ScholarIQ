/* eslint-disable @typescript-eslint/no-require-imports */
// Offline guard for the end-to-end run (never shipped or loaded by the app).
// Loaded with NODE_OPTIONS="--require .../net-guard.cjs". It refuses every
// socket connection and DNS lookup that is not on the local machine, and
// appends each attempt to $SCHOLARIQ_NET_GUARD_LOG so the run can fail if the
// web server tried to reach the network.
"use strict";
const fs = require("node:fs");
const net = require("node:net");
const dns = require("node:dns");

const LOG = process.env.SCHOLARIQ_NET_GUARD_LOG;
const LOCAL = new Set(["localhost", "127.0.0.1", "::1", "0.0.0.0", "::", ""]);

function isLocal(host) {
  if (host === undefined || host === null) return true;
  const name = String(host)
    .replace(/^\[|\]$/g, "")
    .toLowerCase();
  return LOCAL.has(name) || name.startsWith("127.") || name.startsWith("::ffff:127.");
}

function refuse(what, target) {
  if (LOG) {
    const stack = new Error().stack.split("\n").slice(2, 8).join("\n");
    fs.appendFileSync(LOG, `node ${what} ${JSON.stringify(target)}\n${stack}\n\n`);
  }
  return new Error(`Outbound network access is blocked in the offline run: ${target}`);
}

if (LOG) {
  // Record that the guard is active in this process; the run checks for it.
  fs.appendFileSync(LOG.replace("outbound.log", "guards.log"), `node ${process.pid}\n`);
}

const connect = net.Socket.prototype.connect;
net.Socket.prototype.connect = function guardedConnect(...args) {
  const first = Array.isArray(args[0]) ? args[0][0] : args[0];
  const opts = typeof first === "object" && first !== null ? first : null;
  // A path means a local (Unix) socket; a bare number means localhost.
  if (opts && !opts.path && !isLocal(opts.host ?? "localhost")) {
    const err = refuse("connect", opts.host);
    process.nextTick(() => this.destroy(err));
    return this;
  }
  if (typeof first === "number" || typeof first === "string") {
    const host = typeof args[1] === "string" ? args[1] : "localhost";
    if (typeof first === "number" && !isLocal(host)) {
      const err = refuse("connect", host);
      process.nextTick(() => this.destroy(err));
      return this;
    }
  }
  return connect.apply(this, args);
};

for (const target of [dns, dns.promises]) {
  const lookup = target.lookup;
  target.lookup = function guardedLookup(host, ...rest) {
    if (!isLocal(host)) {
      const err = refuse("lookup", host);
      const cb = rest.find((x) => typeof x === "function");
      if (cb) return process.nextTick(() => cb(err));
      return Promise.reject(err);
    }
    return lookup.call(this, host, ...rest);
  };
}
