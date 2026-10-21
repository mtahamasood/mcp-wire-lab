# Fixture walkthrough

#### `tap.spawn.0`
The tap starts the server.

#### `c2s.tools/list.1`
Client asks for tools.

#### `c2s.ping.2`
Client pings.

#### `s2c.notifications/message.0`
Server logs.

#### `c2s.notifications/cancelled.0`
Client cancels tools/list.

#### `stderr.0`
Server prints a boot line.

#### `s2c.response.2`
Answer to ping.

#### `tap.exit.0`
The server exited 0.

