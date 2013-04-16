# vim: ts=4 expandtab
import base64
import cloudinit.util as util
import cloudinit.CloudConfig as cc
import os
import subprocess


__author__ = "Marek Denis <marek.denis@cern.ch>"
__version__ = 0.1


## CONTANTS ##

MODULE_NAME = 'glidein'

class PATHS(object):
    runtime_directory='/tmp/glidein_runtime'
    default_config_directory='/etc/glideinwms'
    default_config_filename='glidein-pilot.ini'
    default_config_file = ''.join([default_config_directory,'/',default_config_filename])
    glidein_userdata_file='glidein_userdata' # file with options for glidein, used internally
    global_userdata_file='user-data' # global file that glidein will eat


class SECTIONS(object):
    vm_properties = 'vm_properties'
    proxy = 'proxy'
    glidein_startup= 'glidein_startup'
    additional_args = 'additional_args'

class PARAMETERS(object):
    param_default_max_lifetime = 'default_max_lifetime'
    param_disable_shutdown = 'disable_shutdown'
    param_contextualize_protocol = 'contextualize_protocol'
    param_ec2_url = 'ec2_url'
    param_user_name = 'user_name'
    param_user_home = 'user_home'
    param_user_ids  = 'user_ids'
    param_args = 'args'
    param_webbase ='webbase'
    param_proxy_file_name = 'proxy_file_name'
    param_proxy ='proxy'
    param_environment = 'environment'

    def __init__(self):
        self.data = dict()

    def key_value_parameter(self,attribute,join_character='='):
        return join_character.join([attribute,self.__getattr__(attribute)])

    def parse(self,cfg):
        """
        1) Setup default values
        2) Add/override values from the /etc/glideinwms/pilot.ini file
        #3) Add/override values from dynamic user-data
        """

        self.__setup_default_values__()
        self.__open_and_parse_etc_config__(PATHS.default_config_file)
        #self.__parse_user_data__(cfg)
    def update(self,values):
        """Adds values to the class-wide dictionary with the parameters"""
        if isinstance(values,dictionary):
            self.data.update(values)
        else:
            raise ValueError("values argument must be a dictionary")


    def __parse_user_data__(self,user_data):
        """
        Thanks to cloud-init we can get this as a dictionary already.
        Just grab the interesting parts
        TODO(marek): Do this recursively
        """
        hierarchy = {SECTIONS.glidein_startup: [param_args,param_webbase],
                     SECTIONS.vm_properties: [param_default_max_lifetime,param_contextualize_protocol,
                                              param_disable_shutdown,param_user_home,param_user_dir,param_user_ids],
                     SECTIONS.proxy: [],
                     SECTIONS.additional_args: []
                    }

        def _get(src,dst,val):
            try:
                dst[val] = src[val]
            except KeyError:
                pass

        for section,subsections in user_data.iteritems():
            if not subsections: # toplevel arg
                _get(user_data,self.data,section)
            else:
                subsection = user_data.get(section, dict())
                for subsection_name in subsections:
                    _get(subsection,self.data,subsection_name)

    def __open_and_parse_etc_config__(self,filename):
        """
        """
        try:
            with open(filename,'r') as fh:
                self.__parse_etc_config__(fh)
        except IOError:
            pass # no such file, I guess? 
    def __parse_etc_config__(self,config):
        """
        The config should be iterable,
        a file object is fine as well
        """
        for line in config:
            if line.startswith('['):
                continue
            line = line.strip()
            key,value = line.split('=',2)
            self.data[key] = value

    def __setup_default_values__(self):
        is self.data:
            return
        self.data[param_default_max_lifetime] = 86400,# 1 day
        self.data[param_disable_shutdown] = False,
        self.data[param_contextualize_protocol] = 'EC2',
        self.data[param_ec2_url] = ''.join([PATHS.runtime_directory,'/',PATHS.global_userdata_file])
        self.data[param_user_name] = 'glidein'
        self.data[param_user_home] = '/scratch/glidein'
        self.data[param_user_ids]  = '509.509'
        self.data[param_proxy_file_name] = 'proxy'

    def __getattr__(self,attribute):
        result = None
        try:
            result = self.data[attribute]
        except (KeyError,AttributeError):
            result = ""
        finally:
            return result


#class GLIDEIN_DEFAULT_VALUES(object):
#    # for default configuration file
#    default_max_lifetime =  86400 # 1 day
#    disable_shutdown = False
#    contextualize_protocol = 'EC2'
#    ec2_url = ''.join([PATHS.runtime_directory,'/',PATHS.global_userdata_file])
#    user_name = 'glidein'
#    user_home = '/scratch/glidein'
#    user_ids = '509.509'
#    # other
#    proxy_file_name = 'proxy'

class MSG(object):
    cannotuse = "Cannot find section %s, will use default values"
    emptyfile = "This file should include proxy key, however it was not set in the contextualization data"
    fatal = "Unhandled exception was caught: %s"
    cannot_base64 = "Cannot decode base64 encoded file, got exception: %s"


def make_key_value(param,dictionary,default=None,join_character='='):
    value = dictionary.get(param,default)
    result=join_character.join([str(param),str(value)])
    return result

def setup_env_variables_str(envvars):
    return '\n'.join(envvars.split())


def handle(_name, cfg, cloud, log, _args):
   """A replacement cloud-init module for running glidein-bootstrap"""
   
   log.info("Starting...")
   if MODULE_NAME not in cfg:
       log.warn("%s not in the user-data, exiting.." % MODULE_NAME)
       return

   glidein_cfg = cfg[MODULE_NAME]
   parameters = PARAMETERS()
   parameters.parse(glidein_cfg)

   ##### VM-PROPERTIES #####
   vm_properties_cfg = None
   try:
       vm_properties_cfg = glidein_cfg[SECTIONS.vm_properties]
       parameters.update(vm_properties_cfg)
   except KeyError:
       print MSG.cannotuse % SECTIONS.vm_properties
       vm_properties_cfg = dict()
   except Exception,e:
       log.error(MSG.fatal % e)
   
   # ensure the directory exists, add an exception? 
   if not os.path.exists(PATHS.default_config_directory):
       os.makedirs(PATHS.default_config_directory)

   glidein_config_file = dict()

   # configurable values from the [DEFAULTS] section
   #default_max_lifetime = make_key_value(PARAMETERS.default_max_lifetime,vm_properties_cfg,default=GLIDEIN_DEFAULT_VALUES.default_max_lifetime)
   #contextualize_protocol = make_key_value(PARAMETERS.contextualize_protocol,vm_properties_cfg,default=GLIDEIN_DEFAULT_VALUES.contextualize_protocol)
   #disable_shutdown = make_key_value(PARAMETERS.disable_shutdown,vm_properties_cfg,default=GLIDEIN_DEFAULT_VALUES.disable_shutdown)
   #ec2_url = make_key_value(PARAMETERS.ec2_url, vm_properties_cfg,default=GLIDEIN_DEFAULT_VALUES.ec2_url) # usually should be empty in the configuration

   default_max_lifetime = parameters.key_value_parameter(PARAMETERS.param_default_max_lifetime)
   contextualize_protocol = parameters.key_value_parameter(PARAMETERS.param_contextualize_protocol)
   disable_shutdown = parameters.key_value_parameter(PARAMETERS.param_disable_shutdown)
   ec2_url = parameters.key_value_parameter(PARAMETERS.param_ec2_url)

   glidein_config_file['[DEFAULTS]'] = [default_max_lifetime,contextualize_protocol,disable_shutdown,ec2_url]

   # configure values from the [GRID_ENV] section
   environment = ''
   try:
       environment = getattr(parameters,PARAMETERS.param_environment)
   except KeyError:
       pass
   except Exception,e:
       log.warn(MSG.fatal % PARAMETERS.environment)
   finally:
       environment = setup_env_variables_str(environment)

   glidein_config_file['[GRID_ENV]'] = [environment]
   
   # default [GLIDEIN_USER] section
   user_name = parameters.key_value_parameter(PARAMETERS.param_user_name)
   user_home = make_key_value(PARAMETERS.param_user_home)
   user_ids = make_key_value(PARAMETERS.param_user_ids)

   glidein_config_file['[GLIDEIN_USER]'] = [user_name,user_home,user_ids]

   with open(PATHS.default_config_file,"w") as fh:
       for k,v in glidein_config_file.iteritems():
           fh.write(k + '\n')
           fh.write('\n'.join(v))
           fh.write('\n')

   ###### GLIDEIN_USERDATA  ######
   
   if not os.path.exists(PATHS.runtime_directory):
       os.makedirs(PATHS.runtime_directory)

   glidein_startup_cfg = None
   try:
       glidein_startup_cfg = glidein_cfg[SECTIONS.glidein_startup]
       properties.update(glidein_startup_cfg)
   except KeyError:
       print MSG.cannotuse % SECTIONS.glidein_startup
       glidein_startup_cfg = dict()
       
   args = parameters.key_value_parameter(PARAMETERS.param_args)
   proxy_file_name = parameters.key_value_parameter(PARAMETERS.param_proxy_file_name)
   webbase = parameters.key_value_parameter(PARAMETERS.param_webbase)

   content = '\n'.join([args,proxy_file_name,webbase])
   with open(PATHS.runtime_directory+'/'+PATHS.glidein_userdata_file,'w') as fh:
       fh.write("[glidein_startup]\n")
       fh.write(content)
   
   ###### PROXY FILE ######

   proxy = None
   try:
       proxy = glidein_cfg[SECTIONS.proxy]
       parameters.update({PARAMETERS.param_proxy:proxy})
   except KeyError:
       print MSG.cannotuse % SECTIONS.proxy
       proxy = base64.b64encode(MSG.emptyfile)
   except Exception,e:
       log.warn(MSG.fatal % e)

   proxy_file = None
   try:
       proxy_file = base64.b64decode(proxy) ## we must decode it
   except TypeError,e:
       log.warn(MSG.cannot_base64 % e)
       proxy_file = MSG.emptyfile

   proxy_file_path = glidein_startup_cfg.get(PARAMETERS.proxy_file_name,GLIDEIN_DEFAULT_VALUES.proxy_file_name)
   with open(PATHS.runtime_directory+'/'+proxy_file_path,'w') as fh:
       fh.write(proxy_file)

   #make a tarball and base64 encode it
   #since Python natively doesn't support tar we must use /bin/tar
   pipe = subprocess.Popen(['/bin/tar', 'czf', '-', proxy_file_path, PATHS.glidein_userdata_file],stdout=subprocess.PIPE,cwd=PATHS.runtime_directory)
   tar_data,_ = pipe.communicate()
   tar_encoded = str(base64.b64encode(tar_data))

   ##### ADDITIONAL ARGUMENTS #####
   additional_args = ''
   try:
       additional_args = str(glidein_cfg[SECTIONS.additional_args])
       parameters.update({PARAMETERS.additional_args,additional_args})
   except KeyError:
       print MSG.cannotuse % SECTIONS.additional_args

   # glidein will eventually eat this file
   with open(PATHS.runtime_directory+'/'+ PATHS.global_userdata_file,'w') as fh:
       fh.write(''.join([tar_encoded,'####',additional_args]))

   log.info("done.")
