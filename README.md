# dev_appserver-python3-windows

## What
This is a patch to allow you run Python 3 Apps on Windows using ```dev_appserver.py```.

## Why
According to [Google](https://cloud.google.com/appengine/docs/standard/testing-and-deploying-your-app?tab=python)

> The dev_appserver tool does not support development of Python 3 apps on Windows.

## How
A high level summary of the changes/code in the patch

1. ```gunicorn``` was replaced with ```waitress``` when OS is Windows since ```gunicorn``` doesn't run on Windows

2. Windows uses the ```Script``` folder instead of ```bin``` folder for storing python executables. ```dev_appserver.py``` included ```bin``` folder in the paths to executable files. This was updated to ```Script``` when OS is Windows.

3. ```dev_appserver.py``` first creates a copy of your requirements file via the command ```tempfile.NamedTemporaryFile()```, adds ```gunicorn``` to the bottom of the copy and then sends this copy to a function which reads the file and installs the requirements. 

...However, Windows doesn't allow reopening of a temporary file via its filename while the file is still open (refer to [documentation](https://docs.python.org/2.7/library/tempfile.html#tempfile.NamedTemporaryFile)) 

... The Patch doesn't create a copy of the requirements file. Instead if installs the contents of the original requirements file and then installs ```waitress```

4. Added the environment variable ```PIP_USER``` and set it to ```False``` because calling ```pip -m install <package_name>``` on Windows via ```subprocess.Popen``` can sometimes lead to the error - '[WinError 5] Access is denied: Consider using the --user option or check the permissions'. 

Setting ```PIP_USER = False``` solves the error
