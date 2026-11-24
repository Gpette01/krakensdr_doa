# KrakenSDR DoA: improvement tasks

This is the task list for the `optimization` branch. It was written before any code change.

- It follows from the audit in [SYSTEM_MAP.md](SYSTEM_MAP.md). Commit audited: `2e1c4e6`, date 2026-11-24.
- The audit produced 115 findings: 33 in the math (P), 55 in the runtime and UI (D), 27 from the offline test work (T). Some findings appear in more than one report, which confirms them independently.
- Every task cites the finding behind it and the `file:line` in the code. File abbreviations (`sp`, `rx`, `kwi`, ...) are defined in SYSTEM_MAP.md.

## How the work runs

1. **One task is one commit.** The commit subject starts with the task ID, so `git log --grep='^M1-02'` finds it.
2. **Bugs first.** A bug task starts with a test that reproduces the bug and fails. The fix must make that same test pass.
3. **Measure, then change.** A speed or accuracy task records the "before" number first, with the benchmark from M0.
4. **The same commit updates this file.** It sets the task status and adds one row to the done log at the bottom. A follow-up fix for a finished task uses the subject `M1-02 follow-up: ...`.
5. **The benefit column holds the measured result.** If a change shows no gain, the row says so.
6. **Nothing here was tested on the real KrakenSDR.** Tasks that need the device are tagged HW and stay open until the owner tests them.
7. **The code is the only source of truth.** Comments, README text and notes are unverified claims. A statement about behavior needs a `file:line` or a test.
8. **Every subagent runs on Opus at high effort.**
9. **Tests are never bent to pass.** No new `skip`, no loosened tolerance, and no regenerated truth data to make a change look good. Golden files change only in tasks whose purpose is numeric.
10. **Nothing in this work may run the start, stop or kill scripts, or the reboot, shutdown, restart and reconfigure callbacks.** Script tasks are checked with `bash -n` and a linter only. Test servers bind to `127.0.0.1` and make no outbound connections.

Team for each task: the physicist defines what "correct" means for math tasks, the developer writes the change, the tester verifies it against the baseline, and the orchestrator reviews the diff and commits.

## Tags and status

| Tag | Meaning |
|---|---|
| OFF | Can be verified fully offline, with synthetic IQ or unit tests. |
| HW | Needs the real device to confirm, fully or partly. |
| DEC | Needs an owner decision first, because it changes an external contract, the security posture, or the product design. |

Status values: `todo`, `doing`, `done`, `blocked`.

Finding confidence, as reported by the audit: **E** = shown by experiment, **R** = shown by reading the code, **H** = hypothesis, not yet confirmed.

## Open decisions for the owner

| # | Decision | Why it matters |
|---|---|---|
| 1 | Which copy is the deployment target: this fork, or one of the other private copies (up to 112 changed lines in the signal processor)? | Decides where finished work must end up. |
| 2 | Which Python environment does the device run? Send `conda list` or `pip freeze`. | With scipy 1.9.3 a frame costs about 29 ms here. With scipy 1.11.4 it costs about 241 ms. The real "before" number depends on this. |
| 3 | May the output contracts change (bearing convention, confidence value, `num_corr_sources`)? | Other programs read these values. Default: keep them as they are, and only add tests. |
| 4 | Security posture: add a login, bind the UI to localhost, or leave it open on the LAN? | The UI runs as root with no login and has reboot and shutdown buttons. |
| 5 | Can the Heimdall DAQ source be added to this machine? | Needed to confirm the control framing bug (M3-01) and to map the DAQ layer. |
| 6 | Stay on Dash 1.20 with `dash_devices` (a 2021 fork), or plan a UI stack move? | The current stack blocks numpy 2 and newer Python versions over time. This would be its own project. |

## M0. Safety net (do this first)

Nothing below can be called "better" or "faster" until these exist. The repo has zero tests today.

| ID | Task | Source | Acceptance check | Tag | Status |
|---|---|---|---|---|---|
| M0-01 | Add pinned requirements files for the two verified environments (Python 3.10 and 3.12) and a test requirements file. | T-17, D-44 | `uv venv` plus install resolves in both. DSP and UI import. | OFF | | done |
| M0-02 | Add `tests/conftest.py`: synthetic plane-wave IQ generator, stub receiver, temp `_share` paths, numba cache redirect. | T-18 | One test drives the real `SignalProcessor.run()` and gets 123 degrees for a 123 degree source. Repo stays clean after the run. | OFF | done |
| M0-03 | Add the truth suite: estimated angle against true angle, for geometry x algorithm x angle. Known bugs are marked `xfail(strict=True)` with their finding ID. | T-02, T-06, T-07 | Suite passes. Each known bug shows as an expected failure. | OFF | todo |
| M0-04 | Add the golden regression: about 40 stored cases with tolerances, plus `--update-golden` that prints a diff table. | T-19 | Two runs in one environment match bit for bit. Cross-environment spectra agree within 0.1 dB. | OFF | todo |
| M0-05 | Add `benchmarks/bench_frame.py`: median, p90 and spread per config, with a per-stage breakdown. Commit the baseline JSON for both environments. | T-01 | Rerun reproduces the medians within max(5 %, 3 x spread). | OFF | todo |
| M0-06 | Add the integration test: a fake DAQ feeds the real receiver over shared memory and FIFOs. | T-03 | 8 of 8 frames give the true angle. The test skips itself if a real DAQ is running. | OFF | todo |
| M0-07 | Add UI tests: layout build for every page, a check that every callback and pushed ID exists, and a server smoke test. | T-15, D-43 | Tests run without a browser. Known broken IDs show as expected failures. | OFF | todo |
| M0-08 | Add Node tests with `node:test` for `_nodejs/index.js`. | T-20, T-21, T-22 | `node --test` runs offline. Known bugs show as expected failures. | OFF | todo |
| M0-09 | Extend CI: run pytest and the Node tests, and pin the `black` version. | D-45 | CI is green on the branch. | OFF | todo |
| M0-10 | Owner collects from the device: the Python package list and `daq_chain_config.ini`. | R5, R6 | Files are sent. The matching baseline is marked as the real one. | HW | todo |

## M1. Bugs that drop frames or crash

Each of these makes the DSP produce no result, or stop, without telling the user.

| ID | Task | Why (finding, where, confidence) | Acceptance check | Tag | Status |
|---|---|---|---|---|---|
| M1-01 | Set the default log level to WARNING. | D-12, `kwi:31-34`, R. The default hides every `logger.error`, so all the bugs below are silent. | A logged error appears in `ui.log` with default settings. | OFF | todo |
| M1-02 | Make TNA compile and run. | P-01, T-02, `sp:1351-1383`, E. numba cannot type the `except` clause. Every frame loses its DoA result when TNA is selected. | Truth suite: TNA finds the source on UCA and ULA. | OFF | todo |
| M1-03 | Build the mixing time axis from an integer sample count. | P-10, T-04, `sp:1287-1295`, E. A float `np.arange` sometimes returns one sample too many, and every frame of that config is dropped. Example: 2.048 MS/s, CPI 65536, 12.5 kHz. | Property test: the length is exact for all valid rate, CPI and bandwidth combinations. | OFF | todo |
| M1-04 | Clamp the source count after spatial smoothing. | P-09, `sp:954-1015`, E. With FBSS and 4 expected sources on a ULA, MUSIC and ROOT-MUSIC raise and every frame is dropped. | Truth suite case for FBSS with the maximum source count gives a result. | OFF | todo |
| M1-05 | Bound the phase mode count of the virtual array transform, and fall back to plain UCA when it is zero. | P-04, `sp:936-944,1528-1616`, E. Below about 227 MHz (radius 0.21 m) every frame raises `ZeroDivisionError`. At 700 MHz and above, bearings are up to 180 degrees wrong. | Truth suite at 144, 433, 700 and 1090 MHz gives the true bearing. | OFF | todo |
| M1-06 | Fix the bounds checks in the custom array generator, and validate the coordinate count in the UI parser. | P-22, T-08, `sp:1654-1668`, E. More coordinates than channels writes past the end of the buffer. The y loop tests the x array. | Test with `NUMBA_BOUNDSCHECK=1` passes for 4, 5 and 6 coordinates. | OFF | todo |
| M1-07 | Use MHz, not Hz, when the settings watcher scales the custom array, and stop rounding coordinates to 1 cm. | D-30, `utils:305-310` against `kwi:111-116`, R. After any settings save the custom array is about one million times too large. | Unit test: startup path and watcher path give the same coordinates at 416.588 MHz. | OFF | todo |
| M1-08 | Give each VFO its own list. | P-24, `sp:163`, R. `[[]] * 16` makes one list shared by all 16 VFOs. | Unit test: appending to VFO 0 leaves VFO 1 empty. | OFF | todo |
| M1-09 | Keep the DSP thread alive on a per-frame exception, and reset `is_running` when it does stop. | D-10, `sp:347-918`, R. Only `sp:481-735` is inside a `try`. Any other exception kills the thread for good, and Stop then hangs. | Test: a stub receiver raises once, and the next frame is still processed. | OFF | todo |
| M1-10 | Handle a closed FIFO in the shared memory reader. | T-03, `shm:214-221`, E. When the DAQ closes the FIFO the DSP thread dies with `struct.error`. | Integration test: the fake DAQ terminates and the DSP thread stays alive. | OFF | todo |
| M1-11 | Replace `np.Infinity` and `np.float_`. | D-44, T-16, P-33, `sp:127`, `kwi:96,105,108`, `utils:294,299,302`, `cb:541,550-551`, E. These names do not exist in numpy 2. | Import and construction pass under numpy 1 and numpy 2. | OFF | todo |
| M1-12 | Define one set of default settings and use it at startup, in the watcher and in Reset. | D-24, section 6.6 of the map, R. The watcher default `vfo_bw = 0` leads to a division by zero at `sp:523-525`. | Test: all three paths yield the same value for every key. | OFF | todo |
| M1-13 | Handle a missing DAQ ini file at startup. | T-11, `kwi:203`, E. A missing file raises `TypeError` and the process hangs. | Test: startup with no ini file logs one error and exits or continues cleanly. | OFF | todo |

## M2. Bugs that give a wrong answer

| ID | Task | Why (finding, where, confidence) | Acceptance check | Tag | Status |
|---|---|---|---|---|---|
| M2-01 | Fix the angle mapping of ROOT-MUSIC on a linear array, and apply the Forward or Backward choice to it. | P-02, T-06, `sp:1442-1449,1488-1490`, E. Sources at 200, 250 and 300 degrees are reported at 20, 70 and 60. | Truth suite: ROOT-MUSIC agrees with MUSIC at 8 test angles. Sign against real antennas: HW (R1). | OFF + HW | todo |
| M2-02 | Apply the array offset once, after estimation, for every algorithm and geometry. | P-03, `sp:1614,1638,1485,1490,1646`, E. One path adds degrees to radians (81 degrees of error at offset 30). ROOT-MUSIC uses the opposite sign. The custom array ignores the offset. | Truth suite at offsets 0, 30 and 90: every path gives the same bearing. Sign against real antennas: HW (R1). | OFF + HW | todo |
| M2-03 | Use the UCA radius directly, not a chord length computed from a stale channel count. | P-15, T-05, `kwi:85-93`, `utils:285`, `cb:532`, E. The DSP uses a radius 1.2 times too large until settings are saved again. MUSIC confidence drops from 25.4 to 8.5. | Test: spacing after a headless start equals the 5-channel value. | OFF | todo |
| M2-04 | Wire up "F-B Toeplitz", or remove it from the UI. | P-16, T-07, `vars:107`, `sp:950-962,1601`, E. The option has no code path. | Two coherent synthetic sources: the option improves on "Off", or it is removed. | OFF | todo |
| M2-05 | Fix the frequency axis used by the "Auto Channel" squelch. | P-20, `sp:503-504`, E. The axis is off by one bin (586 Hz). | Unit test on the axis values. | OFF | todo |
| M2-06 | Use the whole frame for the "All" spectrum mode. | P-19, `sp:465`, E. Only the first 32768 samples are used, so a later burst is invisible to the squelch. | Test: a burst late in the frame opens the squelch. | OFF | todo |
| M2-07 | Use a circular mean when averaging bearings. | P-23, `sp:680-686`, E. 359 and 1 average to 180. | Unit test. | OFF | todo |
| M2-08 | Send per-VFO diagnostics, not the values of VFO 0, and keep infinite SNR out of the JSON. | D-37, D-51, `sp:831-832,1207,1499-1506`, R and H. | Contract test on the JSON for two VFOs. | OFF | todo |
| M2-09 | Report the center frequency of each group when the spectrum is reduced for display. | D-47, `sp:1265-1276`, R. Click-to-tune is biased by up to 3 bins. | Unit test on the reduced axis. | OFF | todo |
| M2-10 | Fix FM demodulation: label the true audio rate, keep filter state across frames, apply AGC once. | P-21, `sp:591-593,645,714`, `su`, E and R. The WAV is labelled 48 kHz when the real rate is 50 kHz at decimation 3. | Synthetic FM tone: the recorded pitch is correct. | OFF | todo |
| M2-11 | Add contract tests that freeze every output format as it is today. | P-25, D-37, section 6.3 of the map, R. CSV and Kerberos send `360 - θ`. XML, JSON and POST send `θ`. | Golden files for all six formats. | OFF | todo |
| M2-12 | Decide one bearing convention for all outputs. | P-25. Changes what other programs receive. | Owner decision 3, then update the golden files. | DEC | todo |
| M2-13 | Replace or remove "number of correlated sources". | P-11, `sp:968`, E. The value is always 0, even for fully coherent sources. | Owner decision 3. Then a test with coherent and incoherent pairs. | DEC | todo |
| M2-14 | Report per-element SNR, or rename the field. | P-12, `sp:1499-1506`, E. The value reads about 7 dB above the true per-element SNR. | Test across 0 to 40 dB. | DEC | todo |
| M2-15 | Replace the peak-to-average confidence with a value that tracks real error. | P-13, `sp:1703`, E. Bartlett reads about 7.4 dB at every SNR. MUSIC changes by 4 dB with grid alignment. | Confidence correlates with the true angle error on synthetic data. Owner decision 3. | DEC | todo |
| M2-16 | Use the header center frequency for each frame. | P-27, `sp:504,511,973`, R. Frames in flight during a retune are processed with the wrong frequency. | HW: retune during reception and check the logs. | HW | todo |

## M3. Robustness: receiver, threads, settings

| ID | Task | Why (finding, where, confidence) | Acceptance check | Tag | Status |
|---|---|---|---|---|---|
| M3-01 | Pad the AGC control message to 128 bytes. | D-13, T-12, P-31, `rx:399-400`, E for the length. The message is 95 bytes. All other commands are 128. | Unit test: every command builder returns 128 bytes. Effect on the DAQ: HW (R3). | OFF + HW | todo |
| M3-02 | Send DAQ commands from one worker thread with a queue, a socket timeout and `try/finally`. | D-14, T-13, `rx:296-333`, R and E. One failure deadlocks all later commands. Commands can also arrive out of order. | Test with a closed peer socket: the next command still runs, and order is kept. | OFF | todo |
| M3-03 | Never block when putting a control reply on the queue. | D-15, `rx:144,170,330`, R. With no browser open, each DAQ command leaks a thread. | Thread count is stable after 10 commands with no consumer. | OFF | todo |
| M3-04 | Store the requested frequency and gain even when the DAQ is disconnected. | D-16, `rx:344-345,373-375`, R. The next save writes the old frequency back. | Unit test with the connection down. | OFF | todo |
| M3-05 | Open the FIFOs without blocking, clear the file descriptors after close, and allow re-init. | D-17, T-10, `shm:150-198`, `rx:94-104,175`, E. If the FIFOs exist and no DAQ runs, startup hangs forever. | Test with a FIFO that has no reader: startup returns within the timeout. | OFF | todo |
| M3-06 | Back off while the DAQ is down, and stop counting failed connects as dropped frames. | D-18, T-09, `sp:355-389`, E. The loop spins with no sleep and the dropped-frame counter reaches thousands in seconds. | Iterations per second with a failing stub stay below 10. | OFF | todo |
| M3-07 | Treat a zero-byte read as end of stream in `eth` mode. | D-19, `rx:244-248,269-273`, R. The loop spins on a closed socket. | Test with a closed socket pair. | OFF | todo |
| M3-08 | Put a copy of the header in each packet. | D-20, T-14, `sp:368`, `rx:210`, E. All 8 consumed packets showed the header of the newest frame. | Test: each packet carries its own `cpi_index`. | OFF | todo |
| M3-09 | Validate the sync word and payload size, and use an explicit struct format. | D-55, `hdr:288-291`, `rx:213-221`, R. | Test with a corrupted header: the frame is rejected with one log line. | OFF | todo |
| M3-10 | Keep all settings across a DAQ reconfigure. | D-08, T-25, `cb:1118-1177`, R. Only 14 fields are copied to the new SignalProcessor. About 30 settings fall back to defaults, and the next save persists them. | Test with a fake DAQ: saved settings are identical before and after. | OFF | todo |
| M3-11 | Stop the old SignalProcessor thread, pool and files on reconfigure. | D-09, `sp:92,215,352`, R. Each reconfigure leaks a thread, a pool and file descriptors. | Thread count is stable across 3 fake reconfigures. | OFF | todo |
| M3-12 | Write `settings.json` atomically, under one lock. | D-23, `kwi:273-354`, `node:130,201`, R. Writers truncate, then write. Readers can see a half-written file. | Stress test with concurrent writers and readers: every read parses. | OFF | todo |
| M3-13 | Make the settings watcher survive a bad value. | D-22, `utils:245-417`, R. One bad number ends the watcher for good. | Test: a bad file is logged, and the watcher runs again. | OFF | todo |
| M3-14 | Reload the nine keys that are saved but never reloaded. | D-23, section 6.6 of the map, R. The next save reverts them. | Test: edit each key in the file, save from the UI, and the edit survives. | OFF | todo |
| M3-15 | Read `rdf_mapper_server` at startup and persist the recording settings. | D-11, `kwi:136-139,270,325`, R. The RDF Mapper URL is reset to a placeholder on every start. | Test: the URL survives a restart. | OFF | todo |
| M3-16 | Validate all DSP callback inputs before changing any state. | D-25, T-26, `cb:550-572,629-634`, R. `array_offset` is guarded by the wrong variable. A bad value leaves the state half-changed. | Unit tests with bad input for each field. | OFF | todo |
| M3-17 | Fix "Update Receiver Parameters" when processing is stopped. | D-26, `callbacks/update_daq_params.py:18-22,55`, R. It raises `UnboundLocalError`. | Unit test with processing stopped. | OFF | todo |
| M3-18 | Return the same type on every path of the DAQ ini writer. | D-27, `kraken_web_config.py:20-22`, `cb:1054`, R. One path returns an int and the caller unpacks a tuple. | Unit test on the error path. | OFF | todo |
| M3-19 | Push preset values to the input IDs, not the label IDs, and remove the 1 s sleep. | D-28, `cb:889-890,901-903`, R. Two DAQ fields never update when a preset is loaded. | ID test: every pushed ID is an input. | OFF | todo |
| M3-20 | Guard the DAQ ini callback against an empty trigger and a cleared checklist. | D-29, `cb:741-743,801-812`, R. | Unit tests. | OFF | todo |
| M3-21 | Replace the 10 ms timer chain with one long-lived UI data thread. | D-21, `utils:91-242`, R. It creates about 100 threads per second, and one exception stops all UI updates for good. | Test: a failing push is logged and the next frame is still pushed. | OFF | todo |
| M3-22 | Remove the public IP lookup from the DSP loop. | D-07, P-26, `sp:864-868`, R. A web request with no timeout runs on the DSP thread once per second in "Full POST" mode. It also sends the station IP to a third party. | Test: a slow network stub does not delay frame processing. | OFF | todo |
| M3-23 | Give output POSTs a timeout, a bounded backlog and error logging. | D-34, `sp:215,855-858,897-900,1209-1216`, R. Errors are discarded and the backlog can grow without limit. | Test with a slow server stub: the backlog stays bounded. | OFF | todo |
| M3-24 | Move GPS polling off the frame path. | D-36, `sp:359-360,1041-1074`, H. A blocking gpsd call runs on every frame. | Test with a fake gpsd that returns no track. | OFF | todo |
| M3-25 | Write output files atomically, limit `status.json` to once per second, and flush the recording file. | D-49, D-35, `sp:342-343,782-784,1135-1136`, R. | Test: a reader never sees a partial file. | OFF | todo |
| M3-26 | Node: connect once in remote mode and clear the ping timer on close. | D-38, T-21, `node:107-110,137-166`, E. Remote mode opens two connections. | Node test counts one connection. | OFF | todo |
| M3-27 | Node: make `/doapost` work after a switch from remote to local mode. | D-39, T-21, `node:169,220,237`, E. It returns 500 and port 8021 never opens. | Node test for the mode switch. | OFF | todo |
| M3-28 | Node: guard `JSON.parse`, build JSON with `JSON.stringify`, serve `public` by absolute path. | D-39, D-04, T-22, `node:96,121-130,188`, E. `GET /` returns 404 today. | Node tests. | OFF | todo |
| M3-29 | Stop only our own processes in `kill.sh`, and stop `miniserve` and the log sync loop too. | D-40, `kill.sh:1-18`, R. The script kills every node and php process on the host. | `shellcheck` is clean. Confirm on the device. | OFF + HW | todo |
| M3-30 | Pass `cwd` to subprocesses, and stop changing the process working directory. | D-41, `cb:387-389,416-418,1077,1092`, R. | Unit test: the working directory is unchanged after the callback. | OFF | todo |
| M3-31 | Send the first GAIN command only after the channel count is known. | T-27, `kwi:244`, `rx:373-386`, E for the empty message. With a channel count of 0 the GAIN message carries no gains. | Test: the first GAIN message holds one value per channel. | OFF | todo |
| M3-32 | Make the spectrum figure reset after a reconfigure take effect. | D-42, `cb:1181-1182`, `utils:228`, R. The reset rebinds a module-local name, so the page keeps the old figure. | Test: after the reset, the pushed figure is the new one. | OFF | todo |
| M3-33 | Fix the off-by-one at the end of `simulation_from_log.js`. | T-23, `_nodejs/simulation_from_log.js:52-54`, R. The loop reads one entry past the end. | Node test with a 3-line log. | OFF | todo |

## M4. Speed

Each task records its "before" number with the M0 benchmark, then changes the code, then records "after". The numbers below come from the audit and are not Raspberry Pi numbers.

| ID | Task | Why (finding, where, confidence) | Before, from the audit | Tag | Status |
|---|---|---|---|---|---|
| M4-01 | Channelizer: cache the filter taps as `complex64` and call `resample_poly` directly. | P-07, T-01, `sp:1323-1331`, E. On scipy 1.11.4, `decimate` recomputes polynomial roots on every call. The output is identical. | Per frame at `N=2^20`: 240.8 ms on scipy 1.11.4, 29.3 ms on scipy 1.9.3. Channelizer stage alone: about 250 ms and 22.5 ms (note 1). At 3 kHz bandwidth on scipy 1.11.4: 7.2 s per call. | OFF | todo |
| M4-02 | Spatial smoothing: compute it from the correlation matrix. | P-08, `sp:959`, E. `pyargus` loops over every sample in Python. The result matches to 1e-15. | 39 ms per frame, against 0.07 ms. | OFF | todo |
| M4-03 | Estimators: vectorize Bartlett, Capon and MEM, and use one Hermitian eigendecomposition per frame. | P-28, `sp:995-1020`, E. Three decompositions of the same matrix run per frame. | 0.45 ms against 0.03 ms per estimator. | OFF | todo |
| M4-04 | Cache the custom array scanning vectors and the virtual array transform. | P-28, `sp:1563-1572,1646-1668`, E. They are rebuilt on every frame. | 1.4 ms per cache miss. | OFF | todo |
| M4-05 | Spectrum page: push only new y values, at a capped rate. | D-32, `kraken_web_spectrum.py:155-202`, E. The full figure is sent to every browser on every frame. | About 240 KB per frame per browser. | OFF | todo |
| M4-06 | Merge the three status pushes into one, and replace the 500 ms poll with an event. | D-33, `utils:420-589`, `views/main.py:32`, R. | 3 pushes per frame, 2 polls per second per browser. | OFF | todo |
| M4-07 | Stop saving settings on page load. | D-33, `cb:173,184,247,480`, R. Each config page load writes `settings.json` at least 4 times. | 4 writes per page load. | OFF | todo |
| M4-08 | Remove small per-frame waste: the unused `eth` frame copy, 360 `np.min` calls in the JSON writer, the preset directory scan on every render. | P-28, D-33, `rx:266,282`, `sp:1161-1207`, R. | To be measured. | OFF | todo |
| M4-09 | Measure a shared FFT channelizer for several active VFOs. | P-07, T-01. Cost today is per VFO. | To be measured with 4 active VFOs. | OFF | todo |
| M4-10 | Run the benchmark on the device, before and after M4. | R6. | Device numbers. | HW | todo |

Note 1: the per-stage profile and the per-frame median come from different runs, so the stage time can exceed the frame median slightly. M0-05 replaces both with one consistent baseline.

## M5. Accuracy

| ID | Task | Why (finding, where, confidence) | Before, from the audit | Tag | Status |
|---|---|---|---|---|---|
| M5-01 | Design the VFO filter to a stopband target. | P-05, P-30, `sp:1281-1318,595`, E. The filter is only 21 dB down where an adjacent channel aliases onto the wanted one. | An interferer one channel away at +30 dB takes over the bearing. | OFF | todo |
| M5-02 | Design the global decimation filter to a stopband target. | P-06, `sp:411`, E. It is 6 dB down at the new band edge. | 12 dB rejection at 0.6 of the new rate. | OFF | todo |
| M5-03 | Interpolate the peak between grid points. | P-14, `sp:1036`, E. The 1 degree grid limits accuracy at every SNR. | 0.23 to 0.32 degrees RMS, against 0.01 to 0.12 with a 3-point fit. | OFF | todo |
| M5-04 | Build the correlation matrix only from samples inside the burst. | P-17, `sp:947`, E. A burst that fills 10 % of the frame loses 4.7 dB of SNR. | 5.3 dB, against 10.0 dB when gated. | OFF | todo |
| M5-05 | Use a robust noise floor for the squelch. | P-18, `sp:261-293`, E. The threshold opens falsely on short frames and rises with band occupancy. | False-open probability 0.47 at CPI 8192. | OFF | todo |
| M5-06 | Compensate the mode magnitudes in the virtual array transform. | P-04, `sp:1555-1572`, E. The model assumes equal magnitudes; the real ones are 0.99, 0.48, 1.0 at 433 MHz. | Coherent-source methods degrade. To be measured with 2 coherent sources. | OFF | todo |
| M5-07 | Check for a DC offset at the default VFO position. | P-32, `sp:154`, H. The default VFO sits at DC and nothing removes DC. | Needs a frame with a terminated input. | HW | todo |

## M6. Security

| ID | Task | Why (finding, where, confidence) | Acceptance check | Tag | Status |
|---|---|---|---|---|---|
| M6-01 | Remove the unused `_nodejs/settings.json` from git. | D-05, T-24, R. It is an upstream sample file with a Kraken Pro key, a station id and coordinates. It came from the upstream project in 2022 and 2023, not from this fork. No code reads it, and `.gitignore` already lists it. | `git ls-files` no longer lists it. | OFF | todo |
| M6-02 | Accept only a plain file name for recordings, stored under `_share/records`. | D-02, `cb:57-88`, `sp:1218-1229`, R. A path such as `../../etc/passwd` is opened for append as root and can be downloaded. | Unit test rejects absolute and parent paths. | OFF | todo |
| M6-03 | Sanitize the station id on the server side. | D-37, `sp:759-770`, R. The value goes unescaped into the CSV. | Unit test with a comma and a newline. | OFF | todo |
| M6-04 | Reject websocket connections from a foreign origin, and ask for confirmation before reboot, shutdown and reset. | D-01, `app.py:36`, `cb:381-418`, R. Any web page a LAN user visits can open the control websocket. | Test: a foreign `Origin` header is refused. | OFF | todo |
| M6-05 | Node: protect `POST /settings` with a token, validate and merge the body, restrict CORS. | D-03, T-20, `node:178,186-208`, E. Any web origin can overwrite `settings.json` today. | Node test: the cross-origin POST is refused. | DEC | todo |
| M6-06 | Node: verify TLS to the map server, and merge remote settings instead of replacing the file. | D-04, `node:105,121-130`, R. | Node test with an invalid message: the file is unchanged. | DEC | todo |
| M6-07 | Run the UI, the file server and Node without root, and choose the bind addresses. | D-01, D-06, `gui_run.sh:14-19,46,51`, R. | Owner decision 4. Confirm on the device. | DEC + HW | todo |
| M6-08 | Run the Heimdall ini check in a child process, not inside the root UI process. | D-52, `vars:41-60`, `kraken_web_config.py:4,59`, R. Code from outside this repo is imported into the root process. | Test with a stub checker: the result is the same and the UI process imports nothing from the DAQ tree. | OFF + HW | todo |

## M7. UI and UX

When three or more UI tasks land in one round, the viewport audit runs afterwards.

| ID | Task | Why (finding, where, confidence) | Acceptance check | Tag | Status |
|---|---|---|---|---|---|
| M7-01 | Fix broken element IDs: two tooltip targets, one pushed ID with no element, one duplicate ID. | D-43, T-15, `utils:569`, `views/daq_config_card.py:145,189`, E. | The ID test from M0-07 passes with no expected failures. | OFF | todo |
| M7-02 | Track the current page per browser. | D-31, `callbacks/display_page.py:27-43`, R. Two browsers on different pages disturb each other. | Test with two clients on different pages. | OFF | todo |
| M7-03 | Show the processing state, stale data and errors in the UI. | D-46, D-50, `sp:142`, `cb:1057`, R. Processing starts by itself and errors go to a hidden element. | The state is visible for: running, stopped, DAQ down, reconfigure failed. | OFF | todo |
| M7-04 | DoA page: show a result per active VFO, and remove the random placeholder points. | D-50, `vars:88-89`, R. | The page shows no data before the first frame, then one value per VFO. | OFF | todo |
| M7-05 | Fix the CSS: the global font-size rule, heading levels, active-link contrast, the 110 % spectrum height, and widths at 375 px. | D-50, `assets/style.css:10-13,70-82,201-245`, R. Rendering not yet checked in a browser. | No horizontal scroll at 375 px. Contrast meets WCAG AA. | OFF | todo |
| M7-06 | Rename the "Reset Configuration" button ID and fix the typos ("Frequecy", "shtudown"). | D-50, R. | Text and IDs are correct. | OFF | todo |
| M7-07 | Persist the system control and beta feature toggles. | D-54, `cb:910-938`, R. | The toggles survive a restart. | OFF | todo |
| M7-08 | Build VFO cards only for active VFOs. | D-33, R. 16 cards are always built. | Config page element count drops. | OFF | todo |
| M7-09 | Split the config page: everyday controls, advanced DAQ settings, and system control. | D-50, R. One page mixes daily controls, expert fields and power buttons. | Owner approves a layout first. | DEC | todo |
| M7-10 | Send a recording download only to the browser that asked for it. | D-48, `cb:79-88`, H. The shared callback may trigger the download in every open browser. | Test with two websocket clients: only the requester receives the download. | OFF | todo |

## M8. Code health

| ID | Task | Why (finding, where, confidence) | Acceptance check | Tag | Status |
|---|---|---|---|---|---|
| M8-01 | Remove `_nodejs/node_modules` from git and rely on `package-lock.json`. | D-45, E. 801 files are committed. | `npm ci` rebuilds it. Node tests pass. | OFF | todo |
| M8-02 | Extract the per-frame work from `run()` into one function. | T-18, `sp:347-928`, E. All frame work sits in one 580-line loop. | Golden regression is unchanged. | OFF | todo |
| M8-03 | Delete dead code. | D-53, P-29, `sp:103,105,126,214,1708-1758`, `vars:79-85`, `hdr:317-352`, `rx:282`, R. | Tests pass. `grep` finds no remaining reference. | OFF | todo |
| M8-04 | Correct or delete comments and names that contradict the code. | P-29, R. Examples: "numba optimized" on a plain numpy function, "MHz" on a value in Hz. | Review. | OFF | todo |
| M8-05 | Make the array type check explicit. | Found while writing the map, `sp:1631`. `elif "ULA":` is always true, so any unknown array type is treated as a linear array. | Unit test: an unknown type raises. | OFF | todo |
| M8-06 | Format the tree with the pinned `black`. | D-45, E. CI would reformat one file today. | `black --check` passes. | OFF | todo |
| M8-07 | Replace the README dependency text with the requirements files. | T-17, E. The README set cannot be installed. | A fresh install from the README works. | OFF | todo |

## Suggested order

1. **M0**, all of it. It creates the tests and the baseline that every later row needs.
2. **M1**, then **M2**: bugs before anything else.
3. **M3**, with M6-02 pulled forward because it is small and safe.
4. **M4**, then **M5**.
5. **M7** and **M8** in between, as small independent commits.
6. DEC tasks wait for the owner decisions above. HW tasks wait for the device.

## Assumptions made in the owner's absence

The owner asked for the full run without questions. These rules replace the open decisions until the owner says otherwise.

| # | Assumption | Applies to |
|---|---|---|
| A1 | This fork and the `optimization` branch are the target. Other copies are not touched. | Decision 1 |
| A2 | Both verified Python environments must pass. Speed results are reported for both. | Decision 2 |
| A3 | Output field names, order, units and scale stay as they are. A value that is provably wrong is corrected in place. | Decision 3, M2-12 to M2-15 |
| A4 | Security changes ship only when they cannot break a legitimate client. The rest is listed under hardware follow-up. | Decision 4, M6 |
| A5 | The array offset keeps the sign that the grid ULA and UCA path has today. | M2-02 |
| A6 | The UI stays on Dash 1.20 with `dash_devices`. | Decision 6 |
| A7 | Tasks that change what another program reads go last in their milestone, so each one can be reverted alone. | M2, M6 |

## Hardware follow-up

Filled in during the run. Each row is something that only the real KrakenSDR, the Heimdall DAQ or a browser on the device can confirm.

| Item | What to check on the device | Related task |
|---|---|---|
| H-01 | Send the device's Python package list and `daq_chain_config.ini`. | M0-10 |
| H-02 | Run the benchmark on the device before and after the speed work. | M4-10 |
| H-03 | Check for a DC offset with a terminated input. | M5-07 |

## Done log

One row per finished task, added by the commit that finishes it.

The commit for a row is the one whose subject starts with the task ID.

| Task | Why we targeted it | Before | Change | Actual benefit (measured) | Verified by |
|---|---|---|---|---|---|
| M0-01 | The README dependency list cannot be installed (T-17), and nothing pinned the working versions. | No requirements file in the repo. The audit saw the README set fail to resolve (dash-bootstrap-components 1.1.0 needs dash>=2). | Added `requirements-py310.txt` and `requirements-py312.txt` (the two verified freeze lists), `requirements-test.txt` (pytest 8.4.2, pytest-timeout 2.4.0), and a "Running the tests" section in README.md. | `uv pip install` exits 0 for both sets. DSP import works in both (numpy 1.23.5 / scipy 1.9.3 / numba 0.56.4 on 3.10.20; numpy 1.26.4 / scipy 1.11.4 / numba 0.60.0 on 3.12.3). `import app` in a sandbox copy registers 42 callbacks in both. | Install and import commands run in both venvs. |
| M0-02 | The DSP had no test seam: all frame work sits inside the endless `run()` loop, and `__init__` writes into the repo (T-18). | No way to run the DSP offline; zero tests. | Added `tests/conftest.py` (numba cache redirect, source paths, `make_sp` and `sp_paths` fixtures with file output under `tmp_path`) and `tests/helpers` (independent plane-wave generator, stub receiver, list queue, ERROR-log capture, case runner). `pyproject.toml` gets the pytest settings and the `slow` marker. | `test_run_loop_finds_a_single_uca_source` drives the real `run()` and gets 123.0 for a 123 degree source in both venvs (5.7 s on 3.10, 6.5 s on 3.12). `git status` after the run shows only the new files. | pytest in .venv310 and .venv312. |
