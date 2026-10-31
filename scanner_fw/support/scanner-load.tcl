# OpenOCD load for the XIAO nRF54L15, used by `west flash` (see CMakeLists.txt).
# The board's nrf54l-load sets RRAMC CONFIG = 0x101 (write enable + 1-word
# write buffer) and never commits the buffer, so the image's tail is lost.
# Write unbuffered, then disable writes again.
proc scanner-load {file} {
	mww 0x5004b500 0x1
	load_image $file
	mww 0x5004b500 0x0
}
