"""Summarize GameBoy PROFILE records from A:\\GBA\\h1gba.log."""
import argparse, json, re
from pathlib import Path

def analyze(path, count_hz=None, environment='unspecified', coarse_only=False):
    text=path.read_bytes().decode('gbk')
    coarse=[]
    for line in text.splitlines():
        if 'PROFILE_RTC_RUN ' not in line: continue
        f=dict(re.findall(r'(\w+)=([^\s]+)',line))
        row={k:int(v) if v.isdecimal() else v for k,v in f.items()}
        # Exiting from an already paused menu dumps the same RTC endpoints
        # again; mark that snapshot rather than counting another game run.
        if coarse and row['reason']=='exit' and coarse[-1]['reason']=='pause':
            keys=('frames','displayed','rtc_start','rtc_end','valid')
            if all(row[k]==coarse[-1][k] for k in keys): row['duplicate_of']=len(coarse)-1
        seconds=row['seconds'];frames=row['interval_frames']
        if row['valid'] and seconds>=5:
            row['approx_logic_fps']=round(frames/seconds,3)
            row['logic_fps_lower']=round(frames/(seconds+1),3)
            row['logic_fps_upper']=round(frames/(seconds-1),3)
        coarse.append(row)
    if coarse_only:
        if not coarse: raise ValueError('No PROFILE_RTC_RUN records; use v0.11.2 or later')
        return {'log':str(path),'environment':environment,'coarse_runs':coarse,'note':'RTC endpoints have 1-second resolution. FPS is approximate; bounds allow endpoint phase uncertainty. No CPU/render/audio cost percentages can be inferred.'}
    rom=''; hz=0; source='unknown'; segments=[]; segment=None; window=None;settings={}
    for line in text.splitlines():
        fields=dict(re.findall(r'(\w+)=([^\s]+)',line))
        if 'ROM_PATH length=' in line: rom=line.split(' path=',1)[1]
        if 'PROFILE_SETTINGS ' in line: settings={k:int(fields[k]) for k in ('scale','skip','sound')}
        if 'PROFILE_CLOCK ' in line:
            if fields.get('ready')!='1': raise ValueError('Profiler clock unavailable: '+line)
            hz=int(fields['hz'])
            source=fields.get('source','unknown')
        if 'PROFILE_BEGIN ' in line:
            if fields.get('fault')!='0':
                reasons={'1':'Unbalanced profiling scopes','2':'Long stall invalidates counter wrap tracking','3':'TCU counter read failed','4':'TCU5 busy at game-loop start'}
                raise ValueError(reasons.get(fields.get('fault'),'Profiler fault '+str(fields.get('fault'))))
            segment={'rom':rom,'reason':fields['reason'],'settings':dict(settings),'clock_source':source,'logged_count_hz':hz,
                'count_hz':count_hz or hz,'clock_override':count_hz is not None,'windows':[]}
            segments.append(segment)
        elif 'PROFILE_WINDOW ' in line:
            if segment is None: raise ValueError('Window outside profile block')
            window={k:int(v) for k,v in fields.items()};window['costs']={}
            segment['windows'].append(window)
        elif 'PROFILE_VIDEO ' in line:
            if window is None or int(fields['window'])!=window['index']: raise ValueError('Video window mismatch')
            detail={k:int(v) for k,v in fields.items()}
            if detail['frames']!=window['displayed']: raise ValueError('Video frame count mismatch')
            window['video_detail']=detail
        elif 'PROFILE_COST ' in line:
            if window is None or int(fields['window'])!=window['index']: raise ValueError('Window mismatch')
            window['costs'][fields['name']]={'ticks':int(fields['ticks']),'calls':int(fields['calls'])}
    if not segments: raise ValueError('No PROFILE records; use --profile build and pause or exit normally')
    for segment in segments:
        hz=segment['count_hz'];windows=segment['windows']
        if not hz: raise ValueError('Missing clock')
        if not windows:
            segment['summary']={'frames':0,'displayed':0,'costs':{},'logic_fps':None,
                                'note':'No new completed frames since the preceding dump; no timing result for this block.'}
            continue
        frames=sum(w['frames'] for w in windows)
        totals={}
        for w in windows:
            if len(w['costs'])!=11: raise ValueError('Incomplete cost records')
            for name,cost in w['costs'].items():
                row=totals.setdefault(name,{'ticks':0,'calls':0})
                row['ticks']+=cost['ticks'];row['calls']+=cost['calls']
        ticks=sum(row['ticks'] for row in totals.values())
        active=sum(row['ticks'] for name,row in totals.items() if name not in ('pacing_wait','loop_other','save_checkpoint'))
        for name,row in totals.items():
            row['ms_per_frame']=round(row['ticks']*1000/hz/frames,6)
            row['loop_percent']=round(row['ticks']*100/ticks,3)
            row['active_percent']=round(row['ticks']*100/active,3) if name not in ('pacing_wait','loop_other','save_checkpoint') else None
        segment['summary']={'frames':frames,'displayed':sum(w['displayed'] for w in windows),
            'measured_loop_seconds':round(ticks/hz,6),'logic_fps':round(frames*hz/ticks,3),
            'core_mean_ms':round(sum(w['core_mean_us']*w['frames'] for w in windows)/frames/1000*segment['logged_count_hz']/hz,6),
            'core_max_ms':round(max(w['core_max_us'] for w in windows)/1000*segment['logged_count_hz']/hz,6),
            'costs':totals}
        if all('video_detail' in w for w in windows):
            vframes=sum(w['video_detail']['frames'] for w in windows)
            segment['summary']['video_detail']={'displayed':vframes,**{
                name+'_ms_per_display':round(sum(w['video_detail'][name+'_ticks'] for w in windows)*1000/hz/vframes,6) if vframes else None
                for name in ('buffer','scale')}}
    return {'log':str(path),'environment':environment,'segments':segments,'coarse_runs':coarse,'note':'Exclusive wall-time scopes include IRQ/OS scheduling without double counting. Pacing includes busy input polling. QEMU captures measure virtual guest time; real-h1 captures measure the physical device.'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('log',type=Path)
    p.add_argument('--output',type=Path);p.add_argument('--count-hz',type=int,help='Explicit correction for historical logs only')
    p.add_argument('--environment',choices=['real-h1','qemu','unspecified'],default='unspecified')
    p.add_argument('--coarse-only',action='store_true',help='RTC frame-rate range only, even if high-resolution clock failed')
    a=p.parse_args()
    try: report=analyze(a.log,a.count_hz,a.environment,a.coarse_only)
    except ValueError as error: p.error(str(error))
    if a.output: a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for s in report.get('segments',[]):
        print(s['rom'],s['reason'],json.dumps(s['summary'],ensure_ascii=True))
    if a.coarse_only: print(json.dumps(report['coarse_runs'],ensure_ascii=True))
if __name__=='__main__': main()
