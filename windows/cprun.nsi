; cprun Windows installer (NSIS 3, Unicode).
;
; Built by windows/build.sh, which defines:
;   VERSION   e.g. 1.0.0
;   STAGE     folder with cprun.exe, python\, lib\cprun\, LICENSE.txt, README.md, examples\
;   OUTFILE   path of the installer to create
;
; Installs per user (no administrator rights) into %LOCALAPPDATA%\Programs\cprun,
; adds that folder to the user's PATH and registers an uninstaller in
; Settings > Apps.

Unicode true
SetCompressor /SOLID lzma
RequestExecutionLevel user

!include "MUI2.nsh"
!include "LogicLib.nsh"

!define APPNAME "cprun"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\cprun"

Name "${APPNAME} ${VERSION}"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Programs\cprun"
InstallDirRegKey HKCU "${UNINST_KEY}" "InstallLocation"
BrandingText "cprun ${VERSION}"

VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=1033 "ProductName" "cprun"
VIAddVersionKey /LANG=1033 "FileDescription" "cprun installer - competitive programming runner"
VIAddVersionKey /LANG=1033 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=1033 "ProductVersion" "${VERSION}"
VIAddVersionKey /LANG=1033 "LegalCopyright" "MIT License"

!define MUI_ABORTWARNING
!define MUI_LANGDLL_ALLLANGUAGES

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${STAGE}\LICENSE.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_TEXT "$(FinishText)"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "Mongolian"

LangString FinishText ${LANG_ENGLISH} "cprun is installed.$\r$\n$\r$\nOpen a NEW terminal (cmd, PowerShell or Windows Terminal) and run:$\r$\n$\r$\n    cprun A.cc$\r$\n$\r$\nOther commands:$\r$\n    cprun A.cc samples 5$\r$\n    cprun A.cc hand$\r$\n    cprun --help"
LangString FinishText ${LANG_MONGOLIAN} "cprun суулгагдлаа.$\r$\n$\r$\nШИНЭ terminal (cmd, PowerShell эсвэл Windows Terminal) нээгээд:$\r$\n$\r$\n    cprun A.cc$\r$\n$\r$\nБусад командууд:$\r$\n    cprun A.cc samples 5$\r$\n    cprun A.cc hand$\r$\n    cprun --help"
LangString NoGpp ${LANG_ENGLISH} "g++ (C++ compiler) was not found on PATH.$\r$\n$\r$\ncprun needs g++ to compile your solutions. Install MinGW-w64, for example:$\r$\n$\r$\n    winget install BrechtSanders.WinLibs.POSIX.UCRT$\r$\n$\r$\nor MSYS2 (https://www.msys2.org) and add its bin folder to PATH.$\r$\n$\r$\nThen open a new terminal and check:  g++ --version"
LangString NoGpp ${LANG_MONGOLIAN} "g++ (C++ compiler) PATH дээр олдсонгүй.$\r$\n$\r$\ncprun таны кодыг compile хийхэд g++ хэрэгтэй. MinGW-w64 суулгана уу, жишээ нь:$\r$\n$\r$\n    winget install BrechtSanders.WinLibs.POSIX.UCRT$\r$\n$\r$\nэсвэл MSYS2 (https://www.msys2.org) суулгаад bin хавтсыг нь PATH-д нэмнэ.$\r$\n$\r$\nДараа нь шинэ terminal нээгээд шалгана:  g++ --version"
LangString PathFailed ${LANG_ENGLISH} "Could not add cprun to PATH automatically. Add this folder to your PATH manually:$\r$\n$\r$\n$INSTDIR"
LangString PathFailed ${LANG_MONGOLIAN} "cprun-ыг PATH-д автоматаар нэмж чадсангүй. Энэ хавтсыг PATH-д гараар нэмнэ үү:$\r$\n$\r$\n$INSTDIR"

Function .onInit
    !insertmacro MUI_LANGDLL_DISPLAY
FunctionEnd

Function un.onInit
    !insertmacro MUI_UNGETLANGUAGE
FunctionEnd

Section "cprun" SecMain
    SectionIn RO
    SetOutPath "$INSTDIR"

    ; Remove files of a previous version so no stale modules are left behind.
    RMDir /r "$INSTDIR\lib"
    RMDir /r "$INSTDIR\python"

    File "${STAGE}\cprun.exe"
    File "${STAGE}\LICENSE.txt"
    File "${STAGE}\README.md"
    SetOutPath "$INSTDIR\python"
    File /r "${STAGE}\python\*.*"
    SetOutPath "$INSTDIR\lib"
    File /r "${STAGE}\lib\*.*"
    SetOutPath "$INSTDIR\examples"
    File /r "${STAGE}\examples\*.*"
    SetOutPath "$INSTDIR"

    WriteUninstaller "$INSTDIR\uninstall.exe"

    ; Add to the user's PATH (done in Python: NSIS strings would truncate long PATHs).
    nsExec::ExecToLog '"$INSTDIR\python\python.exe" -I -m cprun.winsetup add "$INSTDIR"'
    Pop $0
    ${If} $0 != 0
        MessageBox MB_ICONEXCLAMATION|MB_OK "$(PathFailed)" /SD IDOK
    ${EndIf}

    ; Settings > Apps entry
    WriteRegStr HKCU "${UNINST_KEY}" "DisplayName" "cprun"
    WriteRegStr HKCU "${UNINST_KEY}" "DisplayVersion" "${VERSION}"
    WriteRegStr HKCU "${UNINST_KEY}" "Publisher" "cprun contributors"
    WriteRegStr HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKCU "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\cprun.exe"
    WriteRegStr HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
    WriteRegStr HKCU "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\uninstall.exe" /S'
    WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
    WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1
    WriteRegDWORD HKCU "${UNINST_KEY}" "EstimatedSize" 25000

    ; cprun needs g++ to compile solutions: tell the user if it is missing.
    SearchPath $1 "g++.exe"
    ${If} $1 == ""
        MessageBox MB_ICONINFORMATION|MB_OK "$(NoGpp)" /SD IDOK
    ${EndIf}
SectionEnd

Section "Uninstall"
    nsExec::ExecToLog '"$INSTDIR\python\python.exe" -I -m cprun.winsetup remove "$INSTDIR"'
    Pop $0

    RMDir /r "$INSTDIR\python"
    RMDir /r "$INSTDIR\lib"
    RMDir /r "$INSTDIR\examples"
    Delete "$INSTDIR\cprun.exe"
    Delete "$INSTDIR\LICENSE.txt"
    Delete "$INSTDIR\README.md"
    Delete "$INSTDIR\uninstall.exe"
    RMDir "$INSTDIR"

    DeleteRegKey HKCU "${UNINST_KEY}"
SectionEnd
