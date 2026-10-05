#ifndef H1_GB_SYS_TIME_H
#define H1_GB_SYS_TIME_H
/* gnuboy declares an unused host timer in sys.h. H1 timing is in app.c. */
struct timeval { long tv_sec, tv_usec; };
#endif
