SKYBOX RECON — CONSOLIDATED GITHUB UPLOAD PACKAGE

This ZIP combines the Windows launcher/build workflow with the current
architecture and Python model additions:
- Audio codec catalogue and conservative MPEG-TS audio candidate hints
- Two independent tuner session models and coordinator guard
- Service, video PID, audio PID and PCR/PMT data models
- Cognitive receiver, dual-tuner and Wi-Fi AV architecture documentation
- Offline tests for the supplied model/catalogue code

UPLOAD
1. Extract this ZIP.
2. Open the SkyboxRecon-Upload folder.
3. Upload/merge its CONTENTS into the ROOT of https://github.com/BajanBob/skybox
   (do not upload only the enclosing folder).
4. Preserve the .github/workflows/build-windows.yml path.
5. Commit to main, then open Actions and run the Windows build workflow.

IMPORTANT IMPLEMENTATION STATUS
This is a consolidated source/documentation update package, not a finished
receiver application release. The supplied additions include data models and
codec candidate catalogue functions. They do NOT yet implement physical tuner
drivers, MPEG-TS PAT/PMT/SDT/NIT parsing, hardware blind scan, all codec
decoders, video playback, Wi-Fi 6 AV streaming, or verified dual-demodulator
operation. The dual-tuner coordinator deliberately refuses operation unless
both backends report independent RF paths. Verify the actual board and RF/LNB
connections before claiming dual-tuner support.

The audio catalogue is not a claim that every listed codec is DVB-broadcast
carried or decodable by ALi M3510/M3510A hardware. Codec support must be
confirmed by PMT descriptors, installed decoder capability and hardware tests.

SAFETY
Do not use IPL/flash-write operations on a physical receiver until the known
source defects are corrected and the write path is independently validated.
