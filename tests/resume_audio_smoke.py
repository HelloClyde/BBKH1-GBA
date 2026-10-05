"""Execute repeated pause/resume: retain one PCM device, clean up on exit."""
import json
from mips_smoke import Machine, ROOT
from make_test_rom import make_rom
LOG='A:\\GBA\\h1gba.log'
class Repeated(Machine):
    def __init__(self,bda):
        self.opens=self.closes=self.inits=0;self.pauses=0;self.next_pause=6;self.step=0
        path='A:\\GBA\\AUDIO.gba'
        super().__init__(bda,path=path,files={path:make_rom(tone=True)})
    def pcm_init(self,*args):self.inits+=1;return super().pcm_init(*args)
    def pcm_open(self,*args):self.opens+=1;return super().pcm_open(*args)
    def pcm_close(self,*args):self.closes+=1;return super().pcm_close(*args)
    def event(self,code,button,*args):
        log=self.files.get(LOG,b'');paused=log.rfind(b'PAUSE_MENU_BEGIN')>log.rfind(b'PAUSE_MENU_END')
        event=(-1,-1)
        if paused:
            assert not self.audio_active and len(self.audio_initialized)==1
            assert not self.audio_queue
            event=(10,31) if self.step==0 else (9,39)
            self.step+=1
        elif self.blits>=self.next_pause:
            if self.pauses<3:
                self.pauses+=1;self.next_pause=self.blits+6;self.step=0;event=(9,31)
            else:event=(9,24)
        self.word(code,event[0]);self.word(button,event[1]);return 0
def main():
    m=Repeated(ROOT/'dist/H1GBA.bda');m.run()
    assert m.pauses==3 and m.opens==m.closes==m.inits==1
    assert m.blits>=24 and m.audio_observed
    log=m.files[LOG].decode();assert log.count('AUDIO_PAUSE ')==3 and 'APP_END result=0' in log
    assert 'AUDIO_STALL' not in log and 'underruns=0' in log
    result={'ok':True,'pauses':3,'device_opens':m.opens,'device_closes':m.closes,'descriptor_initializations':m.inits,'video_frames':m.blits}
    (ROOT/'build/verification/resume-audio-smoke.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
if __name__=='__main__':main()
