"""Magic functions for running anybody macros"""

# Stdlib
import errno
import os
import sys
import signal
import time
from subprocess import Popen, PIPE
import atexit
from tempfile import NamedTemporaryFile
import numpy as np
import re
from IPython.display import clear_output, HTML, display
import random
import string

# Our own packages
from IPython.core import magic_arguments
from IPython.core.page import page
from IPython.core.magic import  (
    Magics, magics_class, line_magic, cell_magic
)
from IPython.lib.backgroundjobs import BackgroundJobManager
from IPython.utils import py3compat
from IPython.utils.process import arg_split


def script_args(f):
    """single decorator for adding script args"""
    args = [
        magic_arguments.argument(
            '--out', type=str,
            help="""The variable in which to store stdout from the script.
            If the script is backgrounded, this will be the stdout *pipe*,
            instead of the stderr text itself.
            """
        ),
        magic_arguments.argument(
            '--dir', type=str,
            help="""The directory to run the macro commands.
            """
        ),
        magic_arguments.argument(
            '--anybodycon', type=str,
            help="""The the path to to the anybodycon.
            """
        ),
        magic_arguments.argument(
            '--bg', action="store_true",
            help="""Whether to run the script in the background.
            If given, the only way to see the output of the command is
            with --out/err.
            """
        ),
        magic_arguments.argument(
            '--proc', type=str,
            help="""The variable in which to store Popen instance.
            This is used only when --bg option is given.
            """
        ),
        magic_arguments.argument(
            '--dump', action="store_true",
            help="""This will move all 'dump'ed varialbes to the ipython name
            space.
            """
        ),
        magic_arguments.argument(
            '--pager', action="store_true",
            help="""This will open AnyBody console output in the pager instead of the cell
            """
        ),
    ]
    for arg in args:
        f = arg(f)
    return f

@magics_class
class AnyBodyMagics(Magics):
    """Magics for talking to scripts
    
    This defines a base `%%script` cell magic for running a cell
    with a program in a subprocess, and registers a few top-level
    magics that call %%script with common interpreters.
    """

    
    def __init__(self, shell):
        super(AnyBodyMagics,self).__init__(shell)
        self.job_manager = BackgroundJobManager()
        self.bg_processes = []
        atexit.register(self.kill_bg_processes)

    def __del__(self):
        self.kill_bg_processes()
    
    @magic_arguments.magic_arguments()
    @script_args
    @cell_magic("anybody")
    def run_cell(self, line, cell):
        """Run a cell via a shell command
        
        The `%%anybody` invokes the anybody console application on the rest of
        the cell.        
        
        Parameters
        ----------
        --dir <Path>
        --out <output var>        
        --bg <>
        --proc <baground process variable >
        --anybodycon <path to anybodycon>
        
        Examples
        --------
        ::
            In [1]: %%anybody
               ...: load "mymodel.any"
               ...: operation Main.MyStudy.Kinematics
               ...: run
        """
        argv = arg_split(line, posix = not sys.platform.startswith('win'))
        args, dummy = self.run_cell.parser.parse_known_args(argv)
        
        if args.anybodycon:
            if os.path.exists(args.anybodycon):
                abcpath = args.anybodycon
            elif self.shell.user_ns.has_key(args.anybodycon):
                abcpath = self.shell.user_ns[args.anybodycon]
        elif sys.platform == 'win32':
            import _winreg
            try:        
                abpath = _winreg.QueryValue(_winreg.HKEY_CLASSES_ROOT,
                                'AnyBody.AnyScript\shell\open\command')
                abpath = abpath.rsplit(' ',1)[0].strip('"')
                abcpath  = os.path.join(os.path.dirname(abpath),'AnyBodyCon.exe')
            except:
                raise Exception('Could not find AnyBody Modeling System in windows registry')
        else: 
            raise Exception('Cannot find the specified anybodycon')
        if not os.path.exists(abcpath):
            raise Exception('Cannot find the specified anybodycon: %s'%abcpath)


    
        if args.dir and os.path.isdir(args.dir):
            folder = args.dir
        elif self.shell.user_ns.has_key(args.dir):
            folder = self.shell.user_ns[args.dir]
        else:
            folder = os.getcwd()
              
        cell = cell.encode('utf8', 'replace')
        macro = cell if cell.endswith('\n') else cell+'\n'
        macrofile = NamedTemporaryFile(mode='w+b',
                                         prefix ='macro_',
                                         suffix='.anymcr',
                                         dir= folder,
                                         delete = False)
        
        macrofile.write(macro)
        macrofile.flush()

        
        
        
        cmd = [abcpath ,'/d',folder, '--macro=', macrofile.name, '/ni', "1>&2"]        
        
        try:
            p = Popen(cmd, stdout=PIPE, stderr=PIPE, stdin=PIPE, shell= True)
        except OSError as e:
            if e.errno == errno.ENOENT:
                print "Couldn't find program: %r" % cmd[0]
                return
            else:
                raise
        
        if args.bg:
            self.bg_processes.append(p)
            self._gc_bg_processes()
            if args.out:
                self.shell.user_ns[args.out] = p.stderr
            self.job_manager.new(self._run_script, p, macrofile, daemon=True)
            if args.proc:
                self.shell.user_ns[args.proc] = p
            return
        
        random_tag = ''.join( random.sample(string.ascii_uppercase,6) )
        def htmlbox(text):
            raw_html = """<div id="anyscriptbox_{0}" style="height: 120px ; width : auto; border:1px dotted black;padding:0.5em;overflow:auto;background-color:#E0E0E0 ; font:3px Geogia"><font size="2px" face="courier"> {1} </font></div> <script> var myDiv = document.getElementById("anyscriptbox_{0}");
            myDiv.scrollTop = myDiv.scrollHeight;</script> """.format(random_tag, text )
            return HTML(raw_html)
        
        try:
            raw_out = []
            for line in iter(p.stderr.readline,b''):
                line = py3compat.bytes_to_str( line )
                raw_out.append(line)
                if not args.pager:
                    clear_output()
                    display(  htmlbox("<br/>".join( raw_out ) ) )
                #sys.stdout.flush()
                
            if args.pager:
                page("".join(raw_out))
            p.communicate();
                
        except KeyboardInterrupt:
            try:
                p.send_signal(signal.SIGINT)
                time.sleep(0.1)
                if p.poll() is not None:
                    print "Process is interrupted."
                    return
                p.terminate()
                time.sleep(0.1)
                if p.poll() is not None:
                    print "Process is terminated."
                    return
                p.kill()
                print "Process is killed."
            except OSError:
                pass
            except Exception as e:
                print "Error while terminating subprocess (pid=%i): %s" \
                    % (p.pid, e)
            return

        if args.out:
            self.shell.user_ns[args.out] = "\n".join(raw_out)
        
        if args.dump:
            output =  _parse_anybodycon_output( "\n".join(raw_out) )
            if len(output.keys()):
                print 'Dumped variables:'
            for k,v in output.iteritems():
                varname = k.replace('.','_')
                self.shell.user_ns[varname] = v
                print '- ' + varname
        try:
            macrofile.close()            
            os.remove(macrofile.name) 
        except:
            print 'Error removing macro file'    
    
    def _run_script(self, p, macrofile):
        """callback for running the script in the background"""
        p.communicate();
        try:
            macrofile.close()            
            os.remove(macrofile.name) 
        except:
            print 'Error removing macro file'    
        return


    @line_magic("killbganybodycon")
    def killbgscripts(self, _nouse_=''):
        """Kill all BG processes started by %%anybody and its family."""
        self.kill_bg_processes()
        print "All background processes were killed."

    def kill_bg_processes(self):
        """Kill all BG processes which are still running."""
        for p in self.bg_processes:
            if p.poll() is None:
                try:
                    p.send_signal(signal.SIGINT)
                except:
                    pass
        time.sleep(0.1)
        for p in self.bg_processes:
            if p.poll() is None:
                try:
                    p.terminate()
                except:
                    pass
        time.sleep(0.1)
        for p in self.bg_processes:
            if p.poll() is None:
                try:
                    p.kill()
                except:
                    pass
        self._gc_bg_processes()

    def _gc_bg_processes(self):
        self.bg_processes = [p for p in self.bg_processes if p.poll() is None]


def _parse_anybodycon_output(strvar):
    out = {};
    dump_path = None
    previous_line = ""
    for line in strvar.splitlines():
        if previous_line.count('#### Macro command') and previous_line.count('"Dump"'):
            me = re.search('Main[^ \"]*', line)
            if me is not None :
                dump_path = me.group(0)
                
        if line.endswith('='):
            if line.startswith('Main'):
                var_name = line.split('=')[0].strip()
            elif len(var_name):
                var_name.append(line.split('=')[0].strip() )
        
        if line.endswith('};') and line.find('=') == '-1':
            var_name.pop()
                            
        if line.endswith(';') and line.count('=') == 1:
            (first, last) = line.split('=')
            first = first.strip()
            last = last.strip(' ;').replace('{','[').replace('}',']')
            if dump_path is not None:
                first = dump_path
                dump_path = None
            out[first.strip()] = np.array(eval(last))
        if line.startswith('ERROR') or line.startswith('Error'): 
            if line.endswith('Path does not exist.'):
                continue # hack to avoid detecting #path error this error which is always present
            if not out.has_key('error_log'): out['error_log'] = []
            out['error_log'].append(line)
        previous_line = line
    return out


_loaded = False

def load_ipython_extension(ip):
    """Load the extension in IPython."""
    global _loaded
    if not _loaded:
        ip.register_magics(AnyBodyMagics)
        _loaded = True