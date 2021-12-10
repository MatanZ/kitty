#include "jpeg-reader.h"
#include <setjmp.h>

struct error_mgr {
    struct jpeg_error_mgr pub;
    jmp_buf setjmp_buffer;    /* for return to caller */
};

typedef struct error_mgr *error_ptr;


static void error_exit(j_common_ptr cinfo)
{
    error_ptr err=(error_ptr) cinfo->err;
    longjmp(err->setjmp_buffer, 1);
}


unsigned char *
inflate_jpeg_inner(struct jpeg_decompress_struct *cinfo, uint8_t *buf, size_t bufsz) {
    struct error_mgr jerr;
    int rc;
    unsigned char* bmp_buffer = NULL;

    cinfo->err = jpeg_std_error((struct jpeg_error_mgr *)&jerr);
    jerr.pub.error_exit=error_exit;

    if(setjmp(jerr.setjmp_buffer)) {
        jpeg_destroy_decompress(cinfo);
        free(bmp_buffer);
        return NULL;
    }

    jpeg_create_decompress(cinfo);

    jpeg_mem_src(cinfo, buf, bufsz);

    rc = jpeg_read_header(cinfo, TRUE);

    if (!rc) {
        jpeg_destroy_decompress(cinfo);
        return NULL;
    }
    jpeg_start_decompress(cinfo);

    int row_stride = cinfo->output_width * cinfo->output_components;
    int bmp_size = row_stride * cinfo->output_height;
    bmp_buffer = (unsigned char*) malloc(bmp_size);
    while (cinfo->output_scanline < cinfo->output_height) {
        unsigned char *buffer_array[1];
        buffer_array[0] = bmp_buffer + (cinfo->output_scanline) * row_stride;
        jpeg_read_scanlines(cinfo, buffer_array, 1);
    }

    return bmp_buffer;
}

