# dev_appserver-python3-windows

## What
This is a patch to allow you run Python 3 Apps on Windows using ```dev_appserver.py```.

## Why
According to [Google](https://cloud.google.com/appengine/docs/standard/testing-and-deploying-your-app?tab=python)

> The dev_appserver tool does not support development of Python 3 apps on Windows.


## How
A high level summary of the changes/code in the patch

1. ```dev_appserver.py``` runs your App with ```gunicorn``` since this is what Google uses in Production. Since ```gunicorn``` doesn't run on Windows, the Patch replaces it with ```waitress``` when it detects you're running Windows.

2. Windows uses the ```Script``` folder instead of ```bin``` folder for storing python executables. ```dev_appserver.py``` included ```bin``` folder in the paths to executable files. The Patch uses ```Script``` when it detects you're running Windows.

3. ```dev_appserver.py``` first creates a copy of your requirements file via the command ```tempfile.NamedTemporaryFile()```, adds ```gunicorn``` to the bottom of the copy and then sends this copy to a function which reads the file and installs the requirements. 

    However, Windows doesn't allow reopening of a temporary file via its filename while the file is still open ([reference](https://docs.python.org/2.7/library/tempfile.html#tempfile.NamedTemporaryFile)) 

    The Patch doesn't create a copy of the requirements file. Instead it installs the contents of the original requirements file and then installs ```waitress```

4. Added the environment variable ```PIP_USER``` and set it to ```False``` because calling ```pip -m install <package_name>``` on Windows via ```subprocess.Popen()``` can sometimes lead to the error 

    > '[WinError 5] Access is denied: Consider using the --user option or check the permissions'. 


    If you then run ```pip -m --user install <package_name>```, you get another error - 
    
    
    > Can not perform a '--user' install. User site-packages are not visible in this virtualenv.
    
    
    Setting ```PIP_USER = False``` solves all of the above error i.e. it allows you to run ```pip -m install <package_name>``` ([reference](https://github.com/gitpod-io/gitpod/issues/1997#issuecomment-708480259))


## Changed Files

1. instance_factory.py

    Location: 
    
    <CLOUDSK_INSTALL_PATH>\Cloud SDK\google-cloud-sdk\platform\google_appengine\google\appengine\tools\devappserver2\python\

2. http_runtime.py 

    Location: 
    
   <CLOUDSK_INSTALL_PATH>\Cloud SDK\google-cloud-sdk\platform\google_appengine\google\appengine\tools\devappserver2\
   
   
## Installation

For each of the files listed under 'Changed Files', 

1. Navigate to the location

2. Create a backup of the file

3. Download our copy of the file from the 'src' folder and overwrite the original file


When done, run your app with the ```dev_appserver.py``` command as usual i.e. 


```dev_appserver.py --runtime_python_path=<PYTHON3_PATH> --application=<PROJECT_ID> app.yaml --port=<PORT_NO> ```
