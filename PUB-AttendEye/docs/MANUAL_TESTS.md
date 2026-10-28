# Manual tests that need a real webcam and people

Automated tests mock the camera. Run these on the demo laptop and record the result (pass/fail, date, tester) in the table at the bottom. Do not record a pass you did not observe.

1. **Camera permission denied:** block the camera in the browser, press Start Camera. Expect a clear message, no crash.
2. **Camera in use / unplugged:** open another app on the camera, or unplug the webcam while scanning. Expect "camera disconnected" or "in use" message; scanning stops.
3. **Enrollment, consent:** Start is disabled until the consent box is ticked. Enroll a volunteer; expect "Face enrollment completed successfully".
4. **Enrollment problems:** cover the lens (no face), bring a second person into view (multiple faces message), turn the lights off (insufficient quality).
5. **Recognition, enrolled volunteer:** Start Attendance. Expect candidate label, then "Attendance recorded" after ~2 frames. Check Attendance History shows exactly one row.
6. **Duplicate:** stay in view. Expect "Duplicate - already present" and still one row.
7. **Unknown person:** someone not enrolled looks at the camera. Expect "Unknown identity", no attendance, Dashboard unknown count increases.
8. **Uncertain:** try side angle, glasses, distance. Note which produce review cases; confirm one and reject one in the Review Queue.
9. **Photo of a face (spoof):** show a phone photo of an enrolled student. **Expected to be accepted: no liveness check exists.** Record the result honestly and state this limitation in the demo.
10. **Closed session:** end attendance, then try to scan. Expect rejection; no new rows.
11. **Evaluation:** record at least 20 genuine and 20 impostor captures across lighting conditions; read the System Evaluation page and the threshold table.
12. **Export:** export a session CSV and open it in Excel; check names and the absent/pending rows.

| Test | Result | Date | Tester | Notes |
|---|---|---|---|---|
