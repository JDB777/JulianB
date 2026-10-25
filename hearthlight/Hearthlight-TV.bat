@echo off
rem Opens Hearthlight full screen for the TV, in Edge for its natural
rem Dungeon Master voice, with speech allowed to play without a click.
rem Its own Edge profile, so these settings always apply even when Edge is
rem already open, and the mic permission is remembered.
rem First time only: press the Mic button and click Allow once. After that it
rem listens by itself every time it opens. Alt+F4 closes it.
start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" ^
  --kiosk --autoplay-policy=no-user-gesture-required ^
  --user-data-dir="%LOCALAPPDATA%\HearthlightTV" --no-first-run ^
  https://hearthlight-one.vercel.app
