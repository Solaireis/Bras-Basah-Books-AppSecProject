from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    make_response, g as flask_global, abort, jsonify, session  # TODO: session to be removed
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.utils import secure_filename
from SecurityFunctions import encrypt_info, decrypt_info, generate_uuid4, generate_uuid5, sign, verify
from session_handler import create_user_session, get_cookie_value, retrieve_user_session, USER_SESSION_NAME
from users import User
import db_fetch as dbf
import os  # For saving and deleting images
from PIL import Image
from Book import Book
from math import ceil
from OTP import generateOTP
from GoogleEmailSend import gmail_send
from csp import CSP
import pyotp
import time

from forms import (
    SignUpForm, LoginForm, ChangePasswordForm, ResetPasswordForm, ForgetPasswordForm,
    AccountPageForm, CreateUserForm, DeleteUserForm, AddBookForm, OrderForm, OTPForm
)


# CONSTANTS
DEBUG = True  # Debug flag (True when debugging)
ACCOUNTS_PER_PAGE = 10  # Number of accounts to display per page (manage account page)
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}


app = Flask(__name__)
app.config.from_pyfile("config/app.cfg")  # Load config file
app.jinja_env.add_extension("jinja2.ext.do")  # Add do extension to jinja environment
BOOK_IMG_UPLOAD_FOLDER = "static/img/books"
PROFILE_PIC_UPLOAD_FOLDER = "static/img/profile-pic"
app.config["BOOK_UPLOAD_FOLDER"] = BOOK_IMG_UPLOAD_FOLDER  # Set upload folder
app.config["PROFILE_PIC_UPLOAD_FOLDER"] = PROFILE_PIC_UPLOAD_FOLDER

limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["30 per second"]
)

def get_user():
    """ Returns user if cookie is correct, else returns None """

    # Get session cookie from request
    user_session = retrieve_user_session(request)

    # Return None
    if user_session is not None and not user_session.is_expired():

        # Retrieve user id from session
        user_id = user_session.user_id

        # Retrieve user data from database
        user_data = dbf.retrieve_user(user_id)

        # If user is not found
        if user_data is not None:

            # If user is a customer
            if not user_data[5]:
                user_data += dbf.retrieve_customer_details(user_id)

            # Return user object
            return User(*user_data)


""" Before first request """


@app.before_first_request
def before_first_request():
    # Create admin if not in database
    if not dbf.admin_exists():
        # Admin details
        admin_id = generate_uuid5("admin")
        username = "admin"
        email = "admin@vsecurebookstore.com"
        password = "PASS{uNh@5h3d}"

        # Create admin
        dbf.create_admin(admin_id, username, email, password)


""" Before request """


@app.before_request
def before_request():
    flask_global.user = get_user()  # Get user


""" After request """


@app.after_request
def after_request(response):
    user:User = flask_global.user

    # Get expired cookies to be deleted and new cookies to be set
    expired_cookies = flask_global.get("expired_cookies", default=[])
    new_cookies = flask_global.get("new_cookies", default={})

    # It needs to be a list for me to iterate through
    if not isinstance(expired_cookies, list):
        raise TypeError("Expired cookies should be stored in a list")

    # I need name value and value for each new cookie
    if not isinstance(new_cookies, dict):
        raise TypeError("New cookies should be stored in a dictionary")

    # Only renew session if login
    if isinstance(user, User):
        renewed_user_session = create_user_session(user.user_id, user.is_admin)
        new_cookies[USER_SESSION_NAME] = renewed_user_session

    # Default log user out
    else:
        # Remove session cookie
        expired_cookies.append(USER_SESSION_NAME)

    # Delete expired cookies
    for delete_this in expired_cookies:
        response.set_cookie(delete_this, "", expires=0)

    # Set new cookies
    for name, value in new_cookies.items():
        response.set_cookie(name, value)

    # Set CSP to prevent XSS
    response.headers["Content-Security-Policy"] = CSP

    return response


"""    Home Page    """

""" Home page """


@app.route("/")
@limiter.limit("10/second", override_defaults=False)
def home():
    english_books_data = dbf.retrieve_books_by_language("English")
    chinese_books_data = dbf.retrieve_books_by_language("Chinese")
    english = [Book(*data) for data in english_books_data]
    chinese = [Book(*data) for data in chinese_books_data]
    return render_template("home.html", english=english, chinese=chinese)  # optional: books_list=books_list


"""    Login/Sign-up Pages    """

""" Sign up page """


@app.route("/user/sign-up", methods=["GET", "POST"])
@limiter.limit("10/second", override_defaults=False)
def sign_up():
    # If user is already logged in
    if flask_global.user is not None:
        return redirect(url_for("account"))

    # Get sign up form
    sign_up_form = SignUpForm(request.form)

    # Flask global error variable for css
    errors = flask_global.errors = {}

    # Validate sign up form if request is post
    if request.method == "POST":
        if not sign_up_form.validate():
            errors["DisplayFieldError"] = True
            return render_template("user/sign_up.html", form=sign_up_form)

        # Extract data from sign up form
        username = sign_up_form.username.data
        email = sign_up_form.email.data.lower()
        password = sign_up_form.password.data

        # Create new user

        # Ensure that email and username are not registered yet
        if dbf.username_exists(username):
            errors["DisplayFieldError"] = errors["SignUpUsernameError"] = True
            flash("Username taken", "sign-up-username-error")
            return render_template("user/sign_up.html", form=sign_up_form)

        elif dbf.email_exists(email):
            errors["DisplayFieldError"] = errors["SignUpEmailError"] = True
            flash("Email already registered", "sign-up-email-error")
            return render_template("user/sign_up.html", form=sign_up_form)

        elif username.lower() in password.lower():
            errors["DisplayFieldError"] = errors["SignUpPasswordError"] = True
            flash("Password cannot contain username", "sign-up-password-error")
            return render_template("user/sign_up.html", form=sign_up_form)
        
        session["Username"] = username
        session["Email"] = email
        session["Password"] = password

        oneTimePass = generateOTP()
        print(oneTimePass)
        # Send email with OTP
        subject = "OTP for registration"
        message = "Do not reply to this email.\nPlease enter " + oneTimePass + " as your OTP to complete your registration."

        gmail_send(email, subject, message)
        session["OTP"] = oneTimePass
        return redirect(url_for("OTPverification"))


    # Render sign up page
    return render_template("user/sign_up.html", form=sign_up_form)

@app.route("/user/sign-up/OTPverification", methods=["GET", "POST"])
@limiter.limit("10/second", override_defaults=False)
def OTPverification():
    email = session.get("Email")
    username = session.get("Username")
    password = session.get("Password")
    oneTimePass = session.get("OTP")

    OTPformat = OTPForm(request.form)
    print(request.method)
    if request.method == "POST":
        OTPinput = OTPformat.otp.data
        print(OTPinput)
        if oneTimePass == OTPinput:
            # Create new customer
            user_id = generate_uuid5(username)  # Generate new unique user id for customer
            dbf.create_customer(user_id, username, email, password)

            # Create new user session to login (placeholder values were used to create user object)
            flask_global.user = User(user_id, "", "", "", "", 0)

            #Return redirect with session cookie
            return redirect(url_for("home"))

        else:
            flash("Invalid OTP Entered! Please try again!")
            return redirect(url_for("OTPverification"))
    else:
        return render_template("user/OTP.html", form=OTPformat)

""" Login page """


@app.route("/user/login", methods=["GET", "POST"])
@limiter.limit("10/second", override_defaults=False)
def login():
    # If user is already logged in
    if flask_global.user is not None:
        return redirect(url_for("account"))

    login_form = LoginForm(request.form)
    if request.method == "POST":
        if not login_form.validate():
            # Flash login error message
            flash("Your account and/or password is incorrect, please try again", "form-error")
        else:
            # Extract username/email and password from login form
            username = login_form.username.data.lower()
            password = login_form.password.data

            # Check username/email
            user_data = dbf.user_auth(username, password)

            # If user_data is not succesfully retrieved (username/email/password is/are wrong)
            if user_data is None:

                # Flash login error message
                flash("Your account and/or password is incorrect, please try again", "form-error")
                return render_template("user/login.html", form=login_form)

            # If login credentials are correct
            else:
                #Google Authentication insert here -Royston

                # Get user object
                user = User(*user_data)

                # Create session to login
                flask_global.user = user
                return redirect(url_for("home"))

    # Render page
    return render_template("user/login.html", form=login_form)


""" Logout """


@app.route("/user/logout")
@limiter.limit("10/second", override_defaults=False)
def logout():
    flask_global.user = None
    response = make_response()
    return redirect(url_for("home"))


""" Forgot password page """  ### TODO: work on this SpeedFox198


@app.route("/user/password/forget", methods=["GET", "POST"])
@limiter.limit("10/second", override_defaults=False)
def password_forget():
    # Get user
    user:User = flask_global.user

    if user is not None:
        return redirect(url_for("home"))

    # Create form
    forget_password_form = ForgetPasswordForm(request.form)

    if request.method == "POST":
        if not forget_password_form.validate():
            if DEBUG: print("Forget Password: form field invalid")
            session["DisplayFieldError"] = True
        else:
            # Configure noreplybbb02@gmail.com
            # app.config.from_pyfile("config/noreply_email.cfg")
            # mail.init_app(app)

            # Get email
            email = forget_password_form.email.data.lower()

            with shelve.open("database") as db:
                email_to_user_id = retrieve_db("EmailToUserID", db)

            if email in email_to_user_id:
                # Generate token
                token = url_serialiser.dumps(email, salt=app.config["PASSWORD_FORGET_SALT"])

                # Send message to email entered
                msg = Message(subject="Reset Your Password",
                              sender=("BrasBasahBooks", "noreplybbb02@gmail.com"),
                              recipients=[email])
                link = url_for("password_reset", token=token, _external=True)
                msg.html = render_template("emails/_password_reset.html", link=link)
                mail.send(msg)
                if DEBUG: print(f"Sent email to {email}")
            else:
                if DEBUG: print(f"No user with email: {email}")

            flash(f"Verification email sent to {email}")
            return redirect(url_for("login"))

    return render_template("user/password/password_forget.html", form=forget_password_form)


""" Reset password page """  ### TODO: work on this SpeedFox198


@app.route("/user/password/reset/<token>", methods=["GET", "POST"])
@limiter.limit("10/second", override_defaults=False)
def password_reset(token):

    # Get user
    guest = get_user()

    # Only Guest will forget password
    if session["UserType"] != "Guest":
        return redirect(url_for("home"))

    # Get email from token
    try:
        email = url_serialiser.loads(token, salt=app.config["PASSWORD_FORGET_SALT"], max_age=TOKEN_MAX_AGE)
    except BadData as err:  # Token expired or Bad Signature
        if DEBUG: print("Invalid Token:", repr(err))  # print captured error (for debugging)
        return redirect(url_for("invalid_link"))

    with shelve.open("database") as db:
        email_to_user_id = retrieve_db("EmailToUserID", db)
        customers_db = retrieve_db("Customers", db)
        guests_db = retrieve_db("Guests", db)

        # Get user
        try:
            customer = customers_db[email_to_user_id[email]]
        except KeyError:
            if DEBUG: print("No user with email:", email)  # Account was deleted
            return redirect(url_for("invalid_link"))

        # Render form
        reset_password_form = ResetPasswordForm(request.form)
        if request.method == "POST":
            if not reset_password_form.validate():
                session["DisplayFieldError"] = True
            else:
                # Extract password
                new_password = reset_password_form.new_password.data

                # Reset Password
                customer.set_password(new_password)
                if DEBUG: print(f"Reset password for: {customer}")

                # Delete guest account
                guests_db.remove(guest.get_user_id())
                if DEBUG: print(f"Deleted: {guest}")

                # Log in customer
                session["UserID"] = customer.get_user_id()
                session["UserType"] = "Customer"
                if DEBUG: print(f"Logged in: {customer}")

                # Safe changes to database
                db["Customers"] = customers_db
                db["Guests"] = guests_db

                # Flash message and redirect to account page
                flash("Password has been successfully set")
                return redirect(url_for("account"))

    return render_template("user/password/password_reset.html", form=reset_password_form, email=email)


""" Change password page """
## TODO: Template (html) not written yet (dying) ~ @SpeedFox198
## TODO: Run and see if working (check if got bugs)
## NOTE: too tired to check for bugs, someone help me pls ~ @SpeedFox198


@app.route("/user/password/change", methods=["GET", "POST"])
@limiter.limit("10/second", override_defaults=False)
def password_change():

    # Get current user
    user:User = flask_global.user

    # If user is not logged in
    if user is None:
        return redirect(url_for("login"))

    # Flask global error variable for css
    errors = flask_global.errors = {}

    # Get change password form
    change_password_form = ChangePasswordForm(request.form)

    # Validate sign up form if request is post
    if request.method == "POST":
        if not change_password_form.validate():
            errors["DisplayFieldError"] = True

        else:
            # Extract data from sign up form
            current_password = change_password_form.current_password.data
            new_password = change_password_form.new_password.data

            # Password (current) was incorrect, disallow change
            if not dbf.user_auth(user.username, current_password):
                errors["DisplayFieldError"] = errors["CurrentPasswordError"] = True
                flash("Your password is incorrect, please try again", "current-password-error")

            # Current and new passwords are the same, disallow change
            elif current_password == new_password:
                errors["DisplayFieldError"] = errors["NewPasswordError"] = True
                flash("New password should not be the same as current password", "new-password-error")

            # Username is inside new password (insecure), disallow change
            elif user.username.lower() in new_password.lower():
                errors["DisplayFieldError"] = errors["NewPasswordError"] = True
                flash("Password cannot contain username", "new-password-error")

            # Password (current) was correct, change to new password
            else:
                # Change user password
                dbf.change_password(user.user_id, new_password)

                # Sign user out (proccess will be done in @app.after_request)
                flask_global.user = None

                # Flash success message and redirect
                flash("Password has been changed successfully, please login again with your new password.")
                return redirect(url_for("login"))

    return render_template("user/password/password_change.html", form=change_password_form)


@app.route("/user/account/2FA")
@limiter.limit("10/second", override_defaults=False)
def account_2FA():
    user: User = flask_global.user

    if user is None or not user.is_admin:
        abort(403)
    
    totp = pyotp.TOTP('base32secret3232')
    totp.now() # => '492039'

    # OTP verified for current time
    totp.verify('492039') # => True
    time.sleep(30)
    totp.verify('492039') # => False
    pyotp.random_hex() 
    return render_template("user/account/2FA.html")

# Needs to be changed
# TODO: needs to change
# NOTE: sending email is done by Royston
"""Verification page in case"""
# Send verification link page
@app.route("/user/verify")
def verify_send():

    # Get user
    user = get_user()

    # If not customer or email is verified
    if not isinstance(user, Customer) or user.is_verified():
        return redirect(url_for("home"))

    # Configure noreplybbb02@gmail.com
    # app.config.from_pyfile("config/noreply_email.cfg")
    # mail.init_app(app)

    # Get email
    email = user.get_email()

    # Generate token
    token = url_serialiser.dumps(email, salt=app.config["VERIFY_EMAIL_SALT"])

    # Send message to email entered
    msg = Message(subject="Verify Email",
                  sender=("BrasBasahBooks", "noreplybbb02@gmail.com"),
                  recipients=[email])
    link = url_for("verify", token=token, _external=True)
    msg.html = f"Click <a href='{link}'>here</a> to verify your email.<br />(Link expires after 15 minutes)"
    mail.send(msg)

    flash(f"Verification email sent to {email}")
    return redirect(url_for("account"))

#"""2FA by Jason"""
#
#@app.route('/2FA', methods=['GET', 'POST'])
#@limiter.limit("10/second") # to prevent attackers from trying to crack passwords or doing enumeration attacks by sending too many automated requests from their ip address
#def twoFactorAuthenticationSetup():
#    if "userSession" in session:
#        userSession = session["userSession"]
#        userDict = {}
#        db = shelve.open(app.config["DATABASE_FOLDER"] + "\\user", "c")
#        try:
#            if 'Users' in db:
#                userDict = db['Users']
#            else:
#                db.close()
#                print("User data in shelve is empty.")
#                session.clear()
#                return redirect(url_for("home"))
#        except:
#            db.close()
#            print("Error in retrieving Users from user.db")
#            return redirect(url_for("home"))
#
#        # retrieving the object based on the shelve files using the user's user ID
#        userKey, userFound, accGoodStatus, accType = get_key_and_validate(userSession, userDict)
#
#        if userFound and accGoodStatus:
#            create_2fa_form = Forms.twoFAForm(request.form)
#            qrCodePath = "".join(["static/images/qrcode/", userSession, ".png"])
#            qrCodeFullPath = Path(app.root_path).joinpath(qrCodePath)
#            if request.method == "POST" and create_2fa_form.validate():
#                secret = request.form.get("secret")
#                otpInput = sanitise(create_2fa_form.twoFAOTP.data)
#                isValid = pyotp.TOTP(secret).verify(otpInput)
#                print(pyotp.TOTP(secret).now())
#                if isValid:
#                    userKey.set_otp_setup_key(secret)
#                    flash(Markup("2FA setup was successful!<br>You will now be prompted to enter your Google Authenticator's time-based OTP every time you login."), "2FA setup successful!")
#                    db["Users"] = userDict
#                    db.close()
#                    qrCodeFullPath.unlink(missing_ok=True) # missing_ok argument is set to True as the file might not exist (>= Python 3.8)
#                    return redirect(url_for("userProfile"))
#                else:
#                    db.close()
#                    flash("Invalid OTP Entered! Please try again!")
#                    return redirect(url_for("twoFactorAuthenticationSetup"))
#            else:
#                db.close()
#                secret = pyotp.random_base32() # for google authenticator setup key
#
#                imagesrcPath = retrieve_user_profile_pic(userKey)
#
#                if accType == "Teacher":
#                    teacherUID = userSession
#                else:
#                    teacherUID = ""
#
#                # Get shopping cart len
#                shoppingCartLen = len(userKey.get_shoppingCart())
#
#                qrCodeForOTP = pyotp.totp.TOTP(s=secret, digits=6).provisioning_uri(name=userKey.get_username(), issuer_name='CourseFinity')
#                img = qrcode.make(qrCodeForOTP)
#                qrCodeFullPath.unlink(missing_ok=True) # missing_ok argument is set to True as the file might not exist (>= Python 3.8)
#                img.save(qrCodeFullPath)
#                return render_template('users/loggedin/2fa.html', shoppingCartLen=shoppingCartLen, accType=accType, imagesrcPath=imagesrcPath, teacherUID=teacherUID, form=create_2fa_form, secret=secret, qrCodePath=qrCodePath)
#        else:
#            db.close()
#            print("User not found or is banned")
#            session.clear()
#            return redirect(url_for("userLogin"))
#    else:
#        if "adminSession" in session:
#            return redirect(url_for("home"))
#        else:
#            return redirect(url_for("userLogin"))
#
#@app.route('/2FA_disable')
#@limiter.limit("10/second") # to prevent attackers from trying to crack passwords or doing enumeration attacks by sending too many automated requests from their ip address
#def removeTwoFactorAuthentication():
#    if "userSession" in session:
#        userSession = session["userSession"]
#        userDict = {}
#        db = shelve.open(app.config["DATABASE_FOLDER"] + "\\user", "c")
#        try:
#            if 'Users' in db:
#                userDict = db['Users']
#            else:
#                db.close()
#                print("User data in shelve is empty.")
#                session.clear()
#                return redirect(url_for("home"))
#        except:
#            db.close()
#            print("Error in retrieving Users from user.db")
#            return redirect(url_for("home"))
#
#        # retrieving the object based on the shelve files using the user's user ID
#        userKey, userFound, accGoodStatus, accType = get_key_and_validate(userSession, userDict)
#
#        if userFound and accGoodStatus:
#            userKey.set_otp_setup_key("")
#            flash(Markup("2FA has been disabled.<br>You will no longer be prompted to enter your Google Authenticator's time-based OTP upon loggin in."), "2FA disabled!")
#            db["Users"] = userDict
#            db.close()
#            return redirect(url_for("userProfile"))
#        else:
#            db.close()
#            print("User not found or is banned")
#            session.clear()
#            return redirect(url_for("userLogin"))
#    else:
#        if "adminSession" in session:
#            return redirect(url_for("home"))
#        else:
#            return redirect(url_for("userLogin"))
#
#@app.route('/2FA_required', methods=['GET', 'POST'])
#@limiter.limit("10/second") # to prevent attackers from trying to bruteforce the 2FA
#def twoFactorAuthentication():
#    # checks if the user is not logged in
#    if "userSession" not in session and "adminSession" not in session:
#        # for admin login
#        if "adminOTPSession" in session:
#            userID, originFeature = session["adminOTPSession"]
#            adminDict = {}
#            db = shelve.open(app.config["DATABASE_FOLDER"] + "\\admin", "c")
#            try:
#                if 'Admins' in db:
#                    adminDict = db['Admins']
#                    db.close()
#                else:
#                    db.close()
#                    print("User data in shelve is empty.")
#                    session.clear()
#                    return redirect(url_for("home"))
#            except:
#                db.close()
#                print("Error in retrieving Users from user.db")
#                return redirect(url_for("home"))
#
#            userKey, userFound, accActive = admin_get_key_and_validate(userID, adminDict)
#
#            if userFound and accActive:
#                if bool(userKey.get_otp_setup_key()):
#                    create_2fa_form = Forms.twoFAForm(request.form)
#                    if request.method == "POST" and create_2fa_form.validate():
#                        otpInput = sanitise(create_2fa_form.twoFAOTP.data)
#                        secret = userKey.get_otp_setup_key()
#                        isValid = pyotp.TOTP(secret).verify(otpInput)
#                        if isValid:
#                            # requires 2FA time-based OTP to be entered when user is logging in
#                            if originFeature == "adminLogin":
#                                session.pop("2FAUserSession", None)
#                                session["adminSession"] = userID
#                                return redirect(url_for("home"))
#                            else:
#                                session.clear()
#                                return redirect(url_for("home"))
#                        else:
#                            flash("Invalid OTP Entered! Please try again!")
#                            return render_template("users/guest/enter_2fa.html", form=create_2fa_form)
#                    else:
#                        return render_template("users/guest/enter_2fa.html", form=create_2fa_form)
#                else:
#                    print("Unexpected Error: User had disabled 2FA.")
#                    return redirect(url_for("userLogin"))
#            else:
#                print("User not found or is inactive")
#                session.clear()
#                return redirect(url_for("adminLogin"))
#
#        # for user login
#        elif "2FAUserSession" in session:
#            userID, originFeature = session["2FAUserSession"]
#            userDict = {}
#            db = shelve.open(app.config["DATABASE_FOLDER"] + "\\user", "c")
#            try:
#                if 'Users' in db:
#                    userDict = db['Users']
#                    db.close()
#                else:
#                    db.close()
#                    print("User data in shelve is empty.")
#                    session.clear()
#                    return redirect(url_for("home"))
#            except:
#                db.close()
#                print("Error in retrieving Users from user.db")
#                return redirect(url_for("home"))
#
#            userKey, userFound, accGoodStatus, accType = get_key_and_validate(userID, userDict)
#
#            if userFound and accGoodStatus:
#                if bool(userKey.get_otp_setup_key()):
#                    create_2fa_form = Forms.twoFAForm(request.form)
#                    if request.method == "POST" and create_2fa_form.validate():
#                        otpInput = sanitise(create_2fa_form.twoFAOTP.data)
#                        secret = userKey.get_otp_setup_key()
#                        isValid = pyotp.TOTP(secret).verify(otpInput)
#                        if isValid:
#                            # requires 2FA time-based OTP to be entered when user is logging in
#                            if originFeature == "login":
#                                session.pop("2FAUserSession", None)
#                                session["userSession"] = userID
#                                return redirect(url_for("home"))
#                            else:
#                                session.clear()
#                                return redirect(url_for("home"))
#                        else:
#                            flash("Invalid OTP Entered! Please try again!")
#                            return render_template("users/guest/enter_2fa.html", form=create_2fa_form)
#                    else:
#                        return render_template("users/guest/enter_2fa.html", form=create_2fa_form)
#                else:
#                    print("Unexpected Error: User had disabled 2FA.")
#                    return redirect(url_for("userLogin"))
#            else:
#                print("User not found or is banned")
#                session.clear()
#                return redirect(url_for("userLogin"))
#        else:
#            return redirect(url_for("home"))
#    else:
#        return redirect(url_for("home"))
#
#"""End of 2FA by Jason"""

"""    User Pages    """

""" View account page """
# TODO Chung Wai do hehe


@app.route("/user/account", methods=["GET", "POST"])
@limiter.limit("10/second", override_defaults=False)
def account():
    # Get current user
    user: User = flask_global.user

    # If user is not logged in
    if not user:
        return redirect(url_for("login"))

    if user.is_admin:
        abort(404)

    # Get account page form
    account_page_form = AccountPageForm(request.form)

    # Validate account page form if request is post
    if request.method == "POST":

        if not account_page_form.validate():
            name = account_page_form.name
            picture = account_page_form.picture
            phone_number = account_page_form.phone_number

            # Flash error message (only flash the 1st error)
            error = name.errors[0] if name.errors else picture.errors[0] if picture.errors else phone_number.errors[0]
            flash(error, "error")
        else:
            # Flash success message
            flash("Account settings updated successfully")

            # Extract email and password from sign up form
            name = " ".join(account_page_form.name.data.split())
            phone_number = account_page_form.phone_number.data
            profile_pic_filename = user._profile_pic

            # Check files submitted for profile pic
            if "picture" in request.files:
                profile_pic = request.files["picture"]
                if profile_pic and allowed_file(profile_pic.filename):
                    profile_pic_filename = f"{user.user_id}_{profile_pic.filename}"
                    profile_pic.save(os.path.join(app.config['PROFILE_PIC_UPLOAD_FOLDER'], profile_pic_filename))

            # Apparently account details were needed to be split because profile picture is in user table
            account_details = (name, phone_number, user.user_id)
            account_details2 = (profile_pic_filename, user.user_id)
            dbf.update_customer_account(account_details, account_details2)

        # Redirect to prevent form resubmission
        return redirect(url_for("account"))

    # Set username and gender to display
    account_page_form.name.data = user.name
    account_page_form.phone_number.data = user.phone_no
    return render_template("user/account.html",
                           form=account_page_form,
                           display_name=user.display_name,
                           picture_path=user.profile_pic,
                           username=user.username,
                           email=user.email,
                           phone_no=user.phone_no)


"""    Admin Pages    """


def admin_check(mode="regular"):
    user: User = flask_global.user
    """ 2 modes for admin check
        regular (Regular) - normal routes with the HTML, default option
        api (API) - API routes
    """
    if not isinstance(user, User) or not user.is_admin: # Check if no cookie and if user is not admin
        if mode == "regular":
            abort(403)
        elif mode == "api":
            return jsonify(message="The resource you requested does not exist."), 404


# Manage accounts page
@app.route("/admin/manage-accounts", methods=["GET", "POST"])
def manage_accounts():
    admin_check()

    # Flask global error variable for css
    flask_global.errors = {}
    errors = flask_global.errors

    # Get page number
    active_page = request.args.get("page", default=1, type=int)

    # Get sign up form
    create_user_form = CreateUserForm(request.form)
    delete_user_form = DeleteUserForm(request.form)

    form_trigger = "addUserButton"  # id of form to trigger on page load

    # If GET request to page (no forms sent)
    if request.method == "GET":
        form_trigger = ""

    # Else, POST request to delete/create user
    else:

        # If action is to delete user (and POST request is valid)
        if delete_user_form.validate() and delete_user_form.user_id.data:

            # Delete selected user
            user_id = delete_user_form.user_id.data

            # Try deleting the user (False if user doesn't exist)
            deleted_customer = dbf.delete_customer(user_id)

            # If customer exists in database (and is deleted)
            if deleted_customer:
                deleted_customer = User(*deleted_customer)
                # Flash success message
                flash(f"Deleted customer: {deleted_customer.username}")

            # Else user is not in database
            else:
                # Flash warning message
                flash("Customer does not exist", "warning")

            # Redirect to prevent form resubmission
            return redirect(f"{url_for('manage_accounts')}?page={active_page}")

        # If action is to create user (and POST request is valid)
        elif create_user_form.validate():
            # Extract data from sign up form
            username = create_user_form.username.data
            email = create_user_form.email.data.lower()
            password = create_user_form.password.data

            # Ensure that username is not registered yet
            if dbf.username_exists(username):
                errors["DisplayFieldError"] = errors["CreateUserUsernameError"] = True
                flash("Username taken", "create-user-username-error")

            # Ensure that email is not registered yet
            elif dbf.email_exists(email):
                errors["DisplayFieldError"] = errors["CreateUserEmailError"] = True
                flash("Email already registered", "create-user-email-error")

            # If username and email are not used, create customer
            else:
                user_id = generate_uuid5(username)  # Generate new unique user id for customer
                dbf.create_customer(user_id, username, email, password)
                flash(f"Created new customer: {username}")
                return redirect(f"{url_for('manage_accounts')}?page={active_page}")

        # Else, form was invalid
        else:
            errors["DisplayFieldError"] = True

    # Get total number of customers
    customer_count = dbf.number_of_customers()

    # Set page number
    last_page = ceil(customer_count/ACCOUNTS_PER_PAGE) or 1
    if active_page < 1:
        active_page = 1
    elif active_page > last_page:
        active_page = last_page

    # Get users to be displayed
    offset = (active_page-1) * ACCOUNTS_PER_PAGE  # Offset for SQL query
    display_users = [User(*data) for data in dbf.retrieve_these_customers(ACCOUNTS_PER_PAGE, offset)]

    first_index = (active_page-1)*ACCOUNTS_PER_PAGE

    # Get page list
    if last_page <= 5:
        page_list = [i for i in range(1, last_page+1)]
    else:
        center_item = active_page
        if center_item < 3:
            center_item = 3
        elif center_item > last_page - 2:
            center_item = last_page - 2
        page_list = [i for i in range(center_item-2, center_item+2+1)]
    prev_page = active_page-1 if active_page-1 > 0 else active_page
    next_page = active_page+1 if active_page+1 <= last_page else last_page

    # Get entries range
    entries_range = (first_index+1, first_index+len(display_users))

    return render_template(
        "admin/manage_accounts.html",
        display_users=display_users,
        active_page=active_page, page_list=page_list,
        prev_page=prev_page, next_page=next_page,
        first_page=1, last_page=last_page,
        entries_range=entries_range, total_entries=customer_count,
        form_trigger=form_trigger,
        create_user_form=create_user_form,
        delete_user_form=delete_user_form
        )


@app.route('/admin/inventory')
def inventory():
    admin_check()

    inventory_data = dbf.retrieve_inventory()

    # Create book object and store in inventory
    book_inventory = [Book(*data) for data in inventory_data]
    return render_template('admin/inventory.html', count=len(book_inventory), books_list=book_inventory)


def allowed_file(filename):
    # Return true if there is an extension in file, and its extension is in the allowed extensions
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


lang_list = [('', 'Select'), ('English', 'English'), ('Chinese', 'Chinese'), ('Malay', 'Malay'), ('Tamil', 'Tamil')]
category_list = [('', 'Select'), ('Action & Adventure', 'Action & Adventure'), ('Classic', 'Classic'),
                 ('Comic', 'Comic'), ('Detective & Mystery', 'Detective & Mystery')]


@app.route('/admin/add-book', methods=['GET', 'POST'])
def add_book():
    admin_check()

    add_book_form = AddBookForm(request.form)
    add_book_form.language.choices = lang_list
    add_book_form.category.choices = category_list

    # Book cover upload (Code is from Flask documentation https://flask.palletsprojects.com/en/2.1.x/patterns/fileuploads/)

    if request.method == "POST" and add_book_form.validate():
        if 'bookimg' not in request.files:
            flash('There is no image uploaded!')
            return redirect(request.url)

        book_img = request.files['bookimg']

        if book_img == '':
            flash('No selected image')
            return redirect(request.url)

        if book_img and allowed_file(book_img.filename):
            book_id = generate_uuid4()
            book_img_filename = f"{book_id}_{secure_filename(book_img.filename)}"  # Generate unique name string for files
            path = os.path.join(app.config['BOOK_UPLOAD_FOLDER'], book_img_filename)
            book_img.save(path)
            image = Image.open(path)
            resized_image = image.resize((259, 371))
            resized_image.save(path)

            book_details = (book_id,
                            add_book_form.language.data,
                            add_book_form.category.data,
                            add_book_form.title.data,
                            int(add_book_form.qty.data),  # int for sqlite
                            int(add_book_form.price.data),  # int for sqlite
                            add_book_form.author.data,
                            add_book_form.desc.data,
                            book_img_filename)

            dbf.book_add(book_details)
            flash("Book successfully added!")

    return render_template('admin/add_book.html', form=add_book_form)


@app.route('/update-book/<book_id>/', methods=['GET', 'POST'])
def update_book(book_id):

    admin_check()

    # Get specified book
    if not dbf.retrieve_book(book_id):
        abort(404)

    selected_book = Book(*dbf.retrieve_book(book_id)[0])

    update_book_form = AddBookForm(request.form)
    update_book_form.language.choices = lang_list
    update_book_form.category.choices = category_list

    if request.method == 'POST' and update_book_form.validate():

        book_img = request.files['bookimg']

        # If no selected book cover
        book_img_filename = selected_book.img

        if book_img and allowed_file(book_img.filename):
            book_img_filename = f"{generate_uuid4()}_{secure_filename(book_img.filename)}"  # Generate unique name string for files
            path = os.path.join(app.config['BOOK_UPLOAD_FOLDER'], book_img_filename)
            book_img.save(path)
            image = Image.open(path)
            resized_image = image.resize((259, 371))
            resized_image.save(path)

        updated_details = (
            update_book_form.language.data,
            update_book_form.category.data,
            update_book_form.title.data,
            int(update_book_form.qty.data),
            int(update_book_form.price.data),
            update_book_form.author.data,
            update_book_form.desc.data,
            book_img_filename,
            selected_book.book_id  # book id here for WHERE statement in query
        )
        dbf.book_update(updated_details)
        flash("Book successfully updated!")
        return redirect(url_for('inventory'))
    else:
        update_book_form.language.data = selected_book.language
        update_book_form.category.data = selected_book.genre
        update_book_form.title.data = selected_book.title
        update_book_form.author.data = selected_book.author
        update_book_form.price.data = selected_book.price
        update_book_form.qty.data = selected_book.qty
        update_book_form.desc.data = selected_book.desc
        return render_template('admin/update_book.html', form=update_book_form)


@app.route('/delete-book/<book_id>/', methods=['POST'])
def delete_book(book_id):
    admin_check()

    # Deletes book and its cover image
    selected_book = Book(*dbf.retrieve_book(book_id)[0])
    book_cover_img = selected_book.img[1:]  # Strip the leading slash for relative path
    print(book_cover_img)
    if os.path.isfile(book_cover_img):
        os.remove(book_cover_img)
    else:
        print("Book cover does not exist.")
    dbf.delete_book(book_id)
    return redirect(url_for('inventory'))


@app.route("/admin/manage-orders")
def manage_orders():
    admin_check()
    return "sorry for removing your code"

"""    Books Pages    """


@app.route('/book/<book_id>', methods=['GET', 'POST'])
@limiter.limit("10/second", override_defaults=False)
def book_info2(book_id):

    # Get book details
    book_data = dbf.retrieve_book(book_id)

    # Get specified book
    if book_data is None:
        abort(404)

    book = Book(*book_data)

    return render_template('book_info2.html', book=book)


@app.route('/book/<int:id>/reviews/page_<int:reviewPageNumber>')
def book_reviews(id, reviewPageNumber):
    pass


""" Search Results Page """


@app.route("/books/<sort_this>")
@limiter.limit("10/second", override_defaults=False)
def books(sort_this):
    sort_dict = {}
    books_dict = {}
    language_list = []
    inventory_data = dbf.retrieve_inventory()

    sort_by = request.args.get("sort-by", default="", type=str)

    for data in inventory_data:
        book = Book(*data)
        books_dict[book.get_book_id()] = book
        language_list.append(book.get_language())

    if books_dict != {}:
         if sort_this == 'latest':
             books_dict = dict(reversed(list(books_dict.items())))
             sort_dict = books_dict
         elif sort_this == 'name_a_to_z':
             sort_dict = name_a_to_z(books_dict)
         elif sort_this == 'name_z_to_a':
             sort_dict = name_z_to_a(books_dict)
         elif sort_this == 'price_low_to_high':
             sort_dict = price_low_to_high(books_dict)
         elif sort_this == 'price_high_to_low':
             sort_dict = price_high_to_low(books_dict)
         elif sort_this.capitalize() in language_list:
             sort_dict = filter_language(sort_this)
         else:
             sort_dict = books_dict

    q = request.args.get("q", default="", type=str)

    if q:
        for book_id, book in sort_dict.copy().items():
            if not any([s.lower() in book.get_title().lower() for s in q.split()]):
                sort_dict.pop(book_id, None)

    return render_template("books.html", query=q, books_list=sort_dict.values(), language_list=language_list)


def filter_language(language):
    books = {}
    books_dict = {}
    inventory_data = dbf.retrieve_inventory()

    for book in inventory_data:
        if inventory_data[book].get_language() == language:
            books.update({book: inventory_data[book]})
    return books


# Sort name from a to z
def name_a_to_z(inventory_data):
    sort_dict = {}
    unsorted_dict = {}
    if inventory_data != {}:
        for book in inventory_data:
            unsorted_dict.update({book: inventory_data[book].get_title()})
        print(unsorted_dict)
        unsorted_dict = sorted(unsorted_dict.items(), key = lambda kv:(kv[1], kv[0]))
        unsorted_dict = {k: v for k, v in unsorted_dict}
        print(unsorted_dict)

        for id in unsorted_dict:
            if id in inventory_data:
                sort_dict.update({id: inventory_data[id]})
    return sort_dict


# Sort name from z to a
def name_z_to_a(inventory_data):
    sort_dict = {}
    unsorted_dict = {}
    if inventory_data != {}:
        for book in inventory_data:
            unsorted_dict.update({book: inventory_data[book].get_title()})
        print(unsorted_dict)
        unsorted_dict = sorted(unsorted_dict.items(), key = lambda kv:(kv[1], kv[0]), reverse=True)
        unsorted_dict = {k: v for k, v in unsorted_dict}
        print(unsorted_dict)

        for id in unsorted_dict:
            if id in inventory_data:
                sort_dict.update({id: inventory_data[id]})
    return sort_dict


# Sort price from low to high
def price_low_to_high(inventory_data):
    sort_dict = {}
    unsorted_dict = {}
    if inventory_data != {}:
        for book in inventory_data:
            unsorted_dict.update({book: float(inventory_data[book].get_price())})
        print(unsorted_dict)
        unsorted_dict = sorted(unsorted_dict.items(), key = lambda kv:(kv[1], kv[0]))
        unsorted_dict = {k: v for k, v in unsorted_dict}
        print(unsorted_dict)

        for id in unsorted_dict:
            if id in inventory_data:
                sort_dict.update({id: inventory_data[id]})
    return sort_dict


# Sort price from high to low
def price_high_to_low(inventory_data):
    sort_dict = {}
    unsorted_dict = {}
    if inventory_data != {}:
        for book in inventory_data:
            unsorted_dict.update({book: float(inventory_data[book].get_price())})
        print(unsorted_dict)
        unsorted_dict = sorted(unsorted_dict.items(), key = lambda kv:(kv[1], kv[0]), reverse=True)
        unsorted_dict = {k: v for k, v in unsorted_dict}
        print(unsorted_dict)

        for id in unsorted_dict:
            if id in inventory_data:
                sort_dict.update({id: inventory_data[id]})
    return sort_dict


"""    Start of Cart Pages    """


# TODO: SpeedFox198 Marence: maybe shldn't abort 400, and shld reply with {"error":1}
# Add to cart
@app.route("/add-to-cart", methods=['POST'])
@limiter.limit("10/second", override_defaults=False)
def add_to_cart():

    # User is a Class
    user:User = flask_global.user

    if not isinstance(user, User):
        return redirect(url_for("login"))
    elif user.is_admin:
        abort(403)

    user_id = user.user_id

    # Getting book_id and quantity to add
    book_id = request.form['book_id']
    buying_quantity = request.form['quantity']

    # Check if quantity enterred is valid
    try:
        buying_quantity = int(buying_quantity)
    except:
        abort(400)  # Bad Request

    # Ensure quantity is within correct range
    if buying_quantity < 0 or buying_quantity > 10000:
        abort(400)  # Bad Request


    book_data = dbf.retrieve_book(book_id)

    # Check if book exists in database
    if book_data is None:
        abort(400)  # Bad Request

    book = Book(*book_data)

    # if book_id is found
    # Checking if book_id is already in cart
    cart_item = dbf.get_cart_item(user_id, book_id)

    # stock left inside (basically customer can't buy more than this)
    max_quantity = book.qty

    # If book is not in customer's cart
    if cart_item is None:
        buying_quantity = min(max_quantity, buying_quantity)
        # Add to cart
        dbf.add_to_shopping_cart(user_id, book_id, buying_quantity)

    # Else book is already added in customer's cart
    else:
        # Update quantity
        buying_quantity += cart_item[2]
        buying_quantity = min(max_quantity, buying_quantity)
        dbf.update_shopping_cart(user_id, book_id, buying_quantity)

    # Flash success message to user
    flash("Book has been added to your cart")

    return redirect(request.referrer) # Return to catalogue if book_id is not in inventory


""" View Shopping Cart"""


@app.route('/cart')
@limiter.limit("10/second", override_defaults=False)
def cart():

    # User is a Class
    user:User = flask_global.user

    if user is None or not user.is_admin:
        abort(403)

    # Get user_id
    user_id = user.get_user_id()

    # Get cart items
    cart_items = dbf.get_shopping_cart(user_id)
    buy_count = len(cart_items)

    # Get total price
    total_price = 0
    for book_id, quantity in cart_items:
        total_price += dbf.retrieve_book(book_id).get_price() * quantity

    return render_template('cart.html', cart_items=cart_items, buy_count=buy_count, total_price=total_price)
    # user_id = get_user().get_user_id()
    # cart_dict = {}
    # books_dict = {}
    # cart_db = None  # shelve.open('database', 'c')
    # book_db = None  # shelve.open('database')
    # try:
    #     books_dict = book_db['Books']
    #     book_db.close()
    # except:
    #     print("There is no books in the database currently.")
    # buy_count = 0
    # rent_count = 0
    # total_price = 0
    # buy_cart = {}
    # rent_cart = []
    # try:
    #     cart_dict = cart_db['Cart']
    #     print(cart_dict)
    #     books_dict = book_db['Books']
    #     book_db.close()
    # except:
    #     print("Error while retrieving data from cart.db")

    # if user_id in cart_dict:
    #     user_cart = cart_dict[user_id]
    #     if user_cart[0] == '':
    #         print('This user has nothing in the buying cart')
    #     else:
    #         buy_cart = user_cart[0]
    #         # buy_count = len(user_cart[0])
    #         for key in buy_cart:
    #             buy_count += buy_cart[key]
    #             total_price = float(total_price)
    #             total_price += float(buy_cart[key] * books_dict[key].get_price())
    #             total_price = float(("%.2f" % round(total_price, 2)))
    #     if len(user_cart) == 1:
    #         print('This user has nothing in the renting cart')
    #     else:
    #         rent_cart = user_cart[1]
    #         rent_count = len(user_cart[1])
    #         for book in rent_cart:
    #             total_price += float(books_dict[book].get_price()) * 0.1
    #             total_price = float(("%.2f" % round(total_price, 2)))

    # return render_template('cart.html', buy_count=buy_count, rent_count=rent_count, buy_cart=buy_cart,
    #                        rent_cart=rent_cart, books_dict=books_dict, total_price=total_price)

""" Update Shopping Cart """
@app.route('/update-cart/<user_id>', methods=['GET', 'POST'])
@limiter.limit("10/second", override_defaults=False)
def update_cart(user_id):
    # User is a Class
    user: User = flask_global.user

    if user is None or not user.is_admin:
        abort(403)

    # get book_id
    book_id = user.get_book_id()

    # Update quantity
    book_quantity = int(request.form['quantity'])
    if book_quantity == 0:
        # No books in cart, delete cart
        delete_buying_cart(user_id)
    else:
        # update book quantity
        print('Update book quantity: ', str(book_quantity))

    return redirect(request.referrer)
    # cart_dict = cart_db['Cart']
    # buy_cart = cart_dict[user_id][0]
    # book_quantity = int(request.form['quantity'])
    # if book_quantity == 0:
    #     print('Oh no need to delete')
    #     delete_buying_cart(id)
    # else:
    #     buy_cart[id] = book_quantity
    #     print(buy_cart)
    #     cart_dict[user_id][0] = buy_cart
    #     cart_db['Cart'] = cart_dict
    #     print(cart_dict, 'updated database')
    #     cart_db.close()
    # return redirect(request.referrer)


""" Delete Cart """
@app.route("/delete-buying-cart/<user_id>", methods=['GET', 'POST'])
@limiter.limit("100/minute", override_defaults=False)
def delete_buying_cart(user_id):
    dbf.delete_shopping_cart(user_id)
    return redirect(request.referrer)

"""    Order Pages    """

""" Customer Orders Page """


@app.route("/my-orders")
@limiter.limit("10/second", override_defaults=False)
def my_orders():
    db_order = []
    new_order = []
    confirm_order = []
    ship_order = []
    deliver_order = []
    canceled_order = []
    books_dict = {}
    try:
        db = shelve.open('database')
        books_dict = db['Books']
        db_order = db['Order']
        print(db_order, "orders in database")
        db.close()
    except:
        print("There might not have any orders as of now.")
    for order in db_order:
        print(order.get_name(), order.get_rent_item())
        if order.get_order_status() == 'Ordered':
            new_order.append(order)
        elif order.get_order_status() == 'Confirmed':
            confirm_order.append(order)
        elif order.get_order_status() == 'Shipped':
            ship_order.append(order)
        elif order.get_order_status() == 'Delivered':
            deliver_order.append(order)
        elif order.get_order_status() == 'Canceled':
            canceled_order.append(order)
        else:
            print(order, "Wrong order status")

    # display from most recent to the least
    db_order = list(reversed(db_order))
    new_order = list(reversed(new_order))
    confirm_order = list(reversed(confirm_order))
    ship_order = list(reversed(ship_order))
    deliver_order = list(reversed(deliver_order))
    canceled_order = list(reversed(canceled_order))

    print("canceled_order: ", canceled_order)
    return render_template('user/my_orders.html', all_order=db_order, new_order=new_order, \
                           confirm_order=confirm_order, ship_order=ship_order, deliver_order=deliver_order,
                           canceled_order=canceled_order, \
                           books_dict=books_dict)


"""    Miscellaneous Pages    """

""" About Page """


@app.route("/home2")
def about():
    return render_template("about.html")


""" API Routes"""


@app.route("/api", methods=["GET"])
def api_home():
    return jsonify(message="BrasBasahBooks API")


@app.route("/api/login", methods=["POST"])
def api_login():
    try:  # Error handle if user never put username and password key in json body
        username = request.json.get("username")
        password = request.json.get("password")
    except AttributeError:
        return jsonify(message="Please enter username or email, and password"), 400

    if username is None:
        return jsonify(message="Please enter a username or email"), 400
    elif password is None:
        return jsonify(message="Please enter a password"), 400
    elif username is None and password is None:
        return jsonify(message="Please enter username or email, and password"), 400

    user_data = dbf.user_auth(username, password)
    if user_data is None:
        return jsonify(message="Your username and/or password is incorrect, please try again"), 400

    user = User(*user_data)
    flask_global.user = user

    return jsonify(message="Login success!")


@app.route("/api/books/all", methods=["GET"])
def api_all_books():
    books_data = dbf.retrieve_inventory()
    if not books_data:
        return jsonify(message="There are no books."), 404

    output = [dict(book_id=row[0],
                   language=row[1],
                   genre=row[2],
                   title=row[3],
                   quantity=row[4],
                   price=row[5],
                   author=row[6],
                   description=row[7],
                   image=row[8]
                   )
              for row in books_data]
    return jsonify(output)


@app.route("/api/books/<book_id>", methods=["GET"])
def api_single_book(book_id):
    # WIP add more methods e.g. POST, PUT, DELETE
    if request.method == "GET":
        book_data = dbf.retrieve_book(book_id)
        if not book_data:
            return jsonify(message=f"There are no such books with id of {book_id}"), 404

        output = dict(book_id=book_data[0],
                      language=book_data[1],
                      genre=book_data[2],
                      title=book_data[3],
                      quantity=book_data[4],
                      price=book_data[5],
                      author=book_data[6],
                      description=book_data[7],
                      image=book_data[8]
                      )
        return jsonify(output)


@app.route('/api/admin/users/all', methods=["GET"])
def api_all_users():
    users_data = dbf.retrieve_these_customers(limit=0, offset=0)

    if not users_data:
        return jsonify(message="There are currently no users.")

    # Comment out personal info in case of excessive data exposure
    output = [dict(user_id=row[0],
                   username=row[1],
                   email=row[2],
                   # password=row[3],
                   profile_pic=row[4],
                   is_admin=row[5],
                   name=row[6],
                   # credit_card_no=row[7],
                   # address=row[8],
                   # phone_no=row[9],
                   )
              for row in users_data]

    return admin_check("api") or jsonify(output)


"""    Error Handlers    """


# Error handling page
@app.errorhandler(403)
def forbidden(e):
    return render_template("error/403.html")


@app.errorhandler(404)
def page_not_found(e):
    return render_template("error/404.html")


@app.errorhandler(429)
def too_many_request(e):
    return render_template("error/429.html")


"""    Main    """

if __name__ == "__main__":
    app.run(debug=DEBUG)  # Run app
