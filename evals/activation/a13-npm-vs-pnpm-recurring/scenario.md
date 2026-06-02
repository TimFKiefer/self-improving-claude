You've used `npm install` a couple of times in this repo even though we use pnpm.
Each time it creates a package-lock.json that we then have to delete, because only
pnpm-lock.yaml is tracked. It's a minor thing but it keeps coming up — is there a
way to stop that from happening?
