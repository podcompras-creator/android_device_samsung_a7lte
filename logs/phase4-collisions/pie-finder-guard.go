package main

import (
    "android/soong/finder"
    "android/soong/finder/fs"
    "encoding/json"
    "fmt"
    "io/ioutil"
    "log"
    "os"
    "path/filepath"
)

type Row struct { Phase string; Makefiles, Blueprints []string }
func put(root, relative string) {
    path := filepath.Join(root, relative)
    if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil { panic(err) }
    if err := ioutil.WriteFile(path, []byte("# fixture\n"), 0644); err != nil { panic(err) }
}
func scan(root, phase string) Row {
    f, err := finder.New(finder.CacheParams{
        WorkingDirectory: root, RootDirs: []string{"."},
        ExcludeDirs: []string{".git", ".repo"},
        PruneFiles: []string{".out-dir", ".find-ignore"},
        IncludeFiles: []string{"Android.mk", "Android.bp", "Blueprints", "CleanSpec.mk", "TEST_MAPPING"},
    }, fs.OsFs, log.New(ioutil.Discard, "", 0), filepath.Join(root, "db-"+phase))
    if err != nil { panic(err) }
    row := Row{phase, f.FindFirstNamedAt(".", "Android.mk"), f.FindNamedAt(".", "Android.bp")}
    f.Shutdown()
    return row
}
func main() {
    if len(os.Args) != 2 { panic("fixture directory required") }
    root := os.Args[1]
    put(root, "device/samsung/a7lte/Android.mk")
    put(root, "device/samsung/a7lte/Android.bp")
    put(root, ".a7lte-port/android/device/samsung/a7lte/Android.mk")
    put(root, ".a7lte-port/templates/device/a7lte/Android.mk")
    put(root, ".a7lte-port/sources/hal-audit/example/Android.bp")
    rows := []Row{scan(root, "before")}
    if len(rows[0].Makefiles) != 3 || len(rows[0].Blueprints) != 2 { panic("baseline discovery differs") }
    put(root, ".a7lte-port/Android.mk")
    rows = append(rows, scan(root, "make-guard-only"))
    if len(rows[1].Makefiles) != 2 || len(rows[1].Blueprints) != 2 { panic("Android.mk guard semantics differ") }
    put(root, ".a7lte-port/.find-ignore")
    rows = append(rows, scan(root, "find-ignore"))
    if len(rows[2].Makefiles) != 1 || rows[2].Makefiles[0] != "device/samsung/a7lte/Android.mk" { panic("native Makefile missing or mirror leaked") }
    if len(rows[2].Blueprints) != 1 || rows[2].Blueprints[0] != "device/samsung/a7lte/Android.bp" { panic("native Blueprint missing or mirror leaked") }
    b, err := json.MarshalIndent(rows, "", "  ")
    if err != nil { panic(err) }
    fmt.Println(string(b))
    fmt.Println("PASS: exact Pie finder prunes mirror Android.mk and Android.bp while retaining native sibling")
}
