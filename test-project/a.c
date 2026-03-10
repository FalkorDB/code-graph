#include <stdio.h>
#include "/src/ff.h"


/* Create an empty intset. */
intset* intsetNew(void) {
    intset *is = zmalloc(sizeof(intset));
    is->encoding = intrev32ifbe(INTSET_ENC_INT16);
    is->length = 0;
    return is;
}