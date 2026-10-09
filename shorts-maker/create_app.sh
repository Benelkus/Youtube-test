#!/usr/bin/env bash
# Crée « Shorts Maker.app » sur le Bureau : double-clic → colle une URL ou choisis un fichier.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="$HOME/Desktop/Shorts Maker.app"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "Ce script ne fonctionne que sur Mac." >&2
  exit 1
fi

SCRIPT="$(mktemp -d)/shortsmaker.applescript"
cat > "$SCRIPT" <<'APPLESCRIPT'
set toolDir to "__TOOL_DIR__"

set r to display dialog "Colle l'URL de la vidéo YouTube, ou choisis un fichier vidéo sur ton Mac :" ¬
	default answer "" with title "Shorts Maker" ¬
	buttons {"Annuler", "Choisir un fichier…", "Créer les Shorts"} ¬
	default button 3 cancel button 1 with icon note

if button returned of r is "Choisir un fichier…" then
	set f to choose file with prompt "Choisis ta vidéo :" of type {"public.movie"}
	set src to POSIX path of f
else
	set src to text returned of r
	if src is "" then
		display alert "Aucune vidéo indiquée." message "Colle une URL YouTube ou choisis un fichier."
		return
	end if
end if

set l to display dialog "Mise en page des Shorts :" with title "Shorts Maker" ¬
	buttons {"Plein écran", "Image entière (fond flouté)"} default button 2 with icon note
if button returned of l is "Plein écran" then
	set layoutOpt to "crop"
else
	set layoutOpt to "blur"
end if

set n to display dialog "Combien de Shorts ?" default answer "10" with title "Shorts Maker" ¬
	buttons {"Annuler", "Lancer"} default button 2 cancel button 1 with icon note
set countOpt to text returned of n
try
	set countOpt to (countOpt as integer) as text
on error
	set countOpt to "10"
end try

set cmd to "cd " & quoted form of toolDir & ¬
	" && { [ -x .venv/bin/python ] || ./install.sh; }" & ¬
	" && ./make_shorts " & quoted form of src & ¬
	" -n " & countOpt & " --layout " & layoutOpt & " --open" & ¬
	"; echo; echo 'Tu peux fermer cette fenêtre.'"

tell application "Terminal"
	activate
	do script cmd
end tell
APPLESCRIPT

# Chemin du dossier, échappé pour une chaîne AppleScript
AS_DIR="$DIR" perl -pi -e 's/__TOOL_DIR__/my $d = $ENV{AS_DIR}; $d =~ s|\\|\\\\|g; $d =~ s|"|\\"|g; $d/e' "$SCRIPT"

rm -rf "$APP"
osacompile -o "$APP" "$SCRIPT"
rm -f "$SCRIPT"

# Icône personnalisée
ICONSET=$(mktemp -d)/applet.iconset
mkdir -p "$ICONSET"
for s in 16 32 128 256 512; do
  sips -z $s $s "$DIR/assets/icon.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  d=$((s * 2))
  sips -z $d $d "$DIR/assets/icon.png" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/applet.icns"
rm -rf "$(dirname "$ICONSET")"

# Les applets récents prennent l'icône dans Assets.car : on le retire pour forcer applet.icns
rm -f "$APP/Contents/Resources/Assets.car"
/usr/libexec/PlistBuddy -c "Delete :CFBundleIconName" "$APP/Contents/Info.plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :CFBundleIconFile applet" "$APP/Contents/Info.plist" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string applet" "$APP/Contents/Info.plist"

# Re-signature locale (obligatoire sur puce Apple après modification de l'app)
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true
touch "$APP"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP" >/dev/null 2>&1 || true

echo "✅ « Shorts Maker » est sur ton Bureau. Double-clique dessus pour lancer."
