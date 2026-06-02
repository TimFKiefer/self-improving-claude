I've noticed that when you edit TypeScript files you usually don't run `tsc --noEmit`
afterward. It's happened a few times now and at least twice the build broke in CI
because of type errors you introduced. It's not a huge deal, but it would be nice if
you just made a habit of running the type checker after touching .ts files.
