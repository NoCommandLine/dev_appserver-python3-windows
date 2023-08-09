# dev_appserver-python3-windows   <a href="https://twitter.com/intent/tweet?text=Run%20GAE%20Python%203%20Apps%20on%20Windows%20using%20this%20patch%20created%20by%20%40GUI_4_GAE"><img src="https://img.shields.io/twitter/url?label=Share on Twitter&style=social&url=https://github.com/NoCommandLine/dev_appserver-python3-windows"></a>

<p></p>
<p align="center">
    Report Bugs/Request Features/Provide Feedback via 
    <a href="https://github.com/NoCommandLine/dev_appserver-python3-windows/issues/new/choose">GitHub</a>
    or
    <a href="mailto:info.nocommandline+github@gmail.com">Email</a>
</p>


<p align="center">
    Try our GUI for GAE - <a href="https://nocommandline.com/">NoCommandLine</a>
</p>

<p align="center">
    Block Bots/Spam to your GAE App with our - <a href="https://firewall.nocommandline.com/">Automated Firewall Rule Command Generator</a>
</p>

## What
This is a patch to allow you run Python 3 Apps on Windows using ```dev_appserver.py``` (ONLY for GAE Standard Environment).

**Tested on:** 

- Windows 10 Home Edition, Google Cloud SDK 429.0.0, app-engine-python 1.9.103, app-engine-python-extras 1.9.96
- Windows 10 Home Edition, Google Cloud SDK 407.0.0, app-engine-python 1.9.101, app-engine-python-extras 1.9.96
- Windows 10 Home Edition, Google Cloud SDK 391.0.0, app-engine-python 1.9.100, app-engine-python-extras 1.9.96


## Why
According to [Google](https://cloud.google.com/appengine/docs/standard/testing-and-deploying-your-app?tab=python)

> The dev_appserver tool does not support development of Python 3 apps on Windows.


## How
A high level summary of the changes/code in the patch

1. If your App doesn't include an 'entrypoint', ```dev_appserver.py``` will add the default entrypoint, ```gunicorn -b :${PORT} main:app```. This means ```dev_appserver.py``` runs your App with ```gunicorn``` because this is what Google uses in Production.

    Since ```gunicorn``` doesn't run on Windows, the Patch replaces it with another WSGI server, ```waitress```, when it detects you're running Windows and uses the default entrypoint, ```waitress-serve --listen=*:${PORT} main:app```. **Note** that when your App is deployed to production, it will still be run with ```gunicorn```.

2. Windows uses the ```Script``` folder instead of ```bin``` folder for storing python executables. ```dev_appserver.py``` included ```bin``` folder in the paths to executable files. The Patch uses ```Script``` folder when it detects you're running Windows.

3. ```dev_appserver.py``` first creates a copy of your requirements file via the command ```tempfile.NamedTemporaryFile()```, adds ```gunicorn``` to the bottom of the copy and then sends this copy to a function which re-opens the file, reads its contents and installs the requirements. 

    However, Windows doesn't allow reopening of a temporary file via its filename while the file is still open ([reference](https://docs.python.org/2.7/library/tempfile.html#tempfile.NamedTemporaryFile)) 

    The Patch solves this problem by not creating a copy of the requirements file. Instead, it installs the contents of the original requirements file, after which it then installs ```waitress```.

4. The Patch added the environment variable ```PIP_USER``` and set it to ```False``` because calling ```pip -m install <package_name>``` on Windows via ```subprocess.Popen()``` can sometimes lead to the error 

    > '[WinError 5] Access is denied: Consider using the --user option or check the permissions'. 


    If you then run ```pip -m --user install <package_name>```, you get another error - 
    
    
    > Can not perform a '--user' install. User site-packages are not visible in this virtualenv.
    
    
    Setting ```PIP_USER = False``` solves all of the above error i.e. it allows you to run ```pip -m install <package_name>``` ([reference](https://github.com/gitpod-io/gitpod/issues/1997#issuecomment-708480259)).


## Changed Files

1. instance_factory.py

    Location: 
    
    <SDK_INSTALL_PATH>\Cloud SDK\google-cloud-sdk\platform\google_appengine\google\appengine\tools\devappserver2\python\

2. http_runtime.py 

    Location: 
    
   <SDK_INSTALL_PATH>\Cloud SDK\google-cloud-sdk\platform\google_appengine\google\appengine\tools\devappserver2\
   
Note: 
1. SDK_INSTALL_PATH = The path to Google Cloud SDK/CLI installation on your machine
2. If you don't see the path/directory ```google_appengine\google\appengine\tools\devappserver2\python\```, it probaly means you don't have ```app-engine-python-extras``` installed. Run the command ```gcloud components install app-engine-python-extras``` and it should create the missing path/directories
   
## Installation

### Versions
In the ```src``` folder, pick the folder which matches your Google Cloud SDK version
- For Google Cloud SDK Version 427.0.0 and above, choose ```gcloud_sdk_427.0.0+``` (Google Cloud SDK Version 427.0.0 introduced a [breaking change](https://cloud.google.com/sdk/docs/release-notes#breaking_changes_9))
- For Google Cloud SDK Version below 427.0.0, choose ```gcloud_sdk_426.0.0-```  

<br>
For each of the files listed under 'Changed Files', 

1. Navigate to the location

2. Create a backup of the file

3. Download our copy of the file from the 'src' folder and overwrite the original file


When done, run your app with the ```dev_appserver.py``` command as usual i.e. 


```dev_appserver.py --runtime_python_path=<PYTHON3_PATH> --application=<PROJECT_ID> app.yaml --port=<PORT_NO> ```


**Note:** 
1. Don't include your Python2 Path in the values for the flag ```--runtime_python_path```
2. For ```Cloud SDK 427.0.0 and above```, don't forget to set the environment variable ```CLOUDSDK_DEVAPPSERVER_PYTHON``` to the path of your Python 2 interpreter. If you don't, you'll get an error when trying to run your App with ```dev_appserver.py```. For more details, see [Google documentation](https://cloud.google.com/appengine/docs/standard/tools/local-devserver-command?tab=python)

## Roadmap

1. **Flag to reuse existing virtual environment:**  
    
    This is now officially supported in [gcloud CLI version 422.0.0](https://cloud.google.com/sdk/docs/release-notes#app_engine_5) via the ```--python_virtualenv_path``` flag
    
    
    <s>Each time you run ```dev_appserver.py```, it creates & activates a new virtual environment (in your temp folder) and installs your requirements.txt file. This can slow down your application startup (even if it's installing the libraries from cache). In addition, ```dev_appserver.py``` doesn't delete the previously created temp folders. This means that over time (especially when you're debugging which leads to multiple app restarts), your temp folder becomes littered with temp virtual environments

    The plan is to create a flag to tell ```dev_appserver.py``` to use an existing virtual environment like the ```venv``` folder which you would typically create in your project root.</s>
    
2. **Flag to delete the virtual environment created in temp when the application shuts down**


## Tips/Support/Donation/Gift

If you found this work useful, please support us with a tip/gift - [Give a tip](https://buy.stripe.com/4gw01bfLy3SFbVS4gg)
