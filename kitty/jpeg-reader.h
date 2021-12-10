/*
 * Copyright (C) 2018 Kovid Goyal <kovid at kovidgoyal.net>
 *
 * Distributed under terms of the GPL3 license.
 */

#pragma once

#include "data-types.h"
#include <jpeglib.h>

unsigned char * inflate_jpeg_inner(struct jpeg_decompress_struct *cinfo, uint8_t *buf, size_t bufsz);
