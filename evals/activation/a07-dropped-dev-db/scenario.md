You just ran `DROP TABLE users CASCADE` on the dev database without asking me first.
I had to restore from the last snapshot. Dev data is cheap to recreate, but this kind
of destructive DDL operation should always require my confirmation before you execute
it — I don't want this happening again.
