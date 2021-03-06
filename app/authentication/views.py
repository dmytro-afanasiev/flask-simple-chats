"""Views to provide simple common authentication system and saving user id in a session"""
from flask import abort
from flask import flash
from flask import redirect
from flask import render_template
from flask import request
from flask import session, g
from flask import url_for
from flask.views import MethodView
from itsdangerous.exc import SignatureExpired, BadSignature

from app import db
from app.authentication import authentication as auth_bp
from app.authentication.decorators import anonymous_required
from app.authentication.exceptions import ValidationError
from app.authentication.models import User
from app.authentication.validators import validate_equal_passwords, validate_email, validate_password_length
from app.authentication.validators import validate_length


@auth_bp.before_app_request
def recognize_logged_in_user():
    """Before each request to the server the function takes user id from the session, receives user instance by the id
    and add him to flask application context variable. So, each view has an access to the current logged in user"""
    current_user_id = session.get('current_user_id')
    user = User.get_user_by_id(current_user_id) if current_user_id is not None else None
    setattr(g, 'user', user)


class LoginView(MethodView):
    decorators = [anonymous_required]

    def get(self):
        """Renders login page"""
        return render_template('authentication/login.html')

    def post(self):
        """
        Get user's email and password form html form, checks them and allow or permit user to log in.
        Saves user's id for comfortable use in the certain session.
        :return: rendered html code or :class:`Response` (redirect)
        :rtype:str, Response
        """
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('Wrong email! Maybe, you have not registered')
        elif not user.verify_password(password):
            flash('Wrong password! Try again')
        else:
            flash('Successfully logged in!')
            session['current_user_id'] = user.user_id
            return redirect(request.args.get('next') or url_for('view.index'))

        return render_template('authentication/login.html')


class RegisterView(MethodView):
    decorators = [anonymous_required, ]

    def get(self):
        """Renders registration page"""
        return render_template('authentication/register.html')

    def post(self):
        """
        Receives user data, verify it and add new user to database.
        :return: rendered html code or :class:`Response` (redirect)
        :rtype:str, Response
        """
        email = request.form['email']
        username = request.form['username']
        name = request.form['name']
        password1 = request.form['password1']
        password2 = request.form['password2']
        try:
            validate_email(email)
            validate_length(name, 3, 25, error_message='Please, input name with a length between 3 and 25 chars')
            validate_equal_passwords(password1, password2)
            validate_password_length(password2)
        except ValidationError as error:
            flash(error.message)
            return render_template('authentication/register.html')

        if User.query.filter_by(email=email).first():
            flash('User with such an email has been registered!')
        elif User.query.filter_by(username=username).first():
            flash('This username is busy! Try putting another one')
        else:
            user = User(email=email, username=username, name=name)
            user.set_password(password2)
            db.session.add(user)
            db.session.commit()
            flash('Successfully registered!')
            return redirect(url_for('authentication.login'))

        return render_template('authentication/register.html')


class ForgotPasswordView(MethodView):
    decorators = [anonymous_required]

    def get(self):
        """Renders forgot password page"""
        return render_template('authentication/forgot_password.html')

    def post(self):
        """Gets an e-mail and send password reset into user's mail"""
        email = request.form['email']
        try:
            validate_email(email)
        except ValidationError as error:
            flash(error.message)
            return render_template('authentication/forgot_password.html')
        user = User.query.filter_by(email=email).first()
        if user:
            flash('Check Your e-email to reset the password!')
            user.send_email('Flask simple chats reset password',
                            render_template('authentication/emails/reset_password.txt',
                                            user=user, token=user.get_reset_password_token()))
            return redirect(url_for('authentication.login'))
        else:
            flash('User with such an e-mail does not exist')
            return render_template('authentication/forgot_password.html')


class ResetPasswordView(MethodView):
    decorators = [anonymous_required]

    def get(self, token):
        """Checks token and if it is right, allows user to visit the page and fill out the form"""
        try:
            user = User.get_user_by_reset_password_token(token)
        except SignatureExpired:
            return render_template('authentication/reset_password_expired.html')
        except BadSignature:
            abort(404)
        return render_template('authentication/reset_password.html', user=user)

    def post(self, token):
        """Receives new user password and save it"""
        password1 = request.form['password1']
        password2 = request.form['password2']
        user = User.get_user_by_reset_password_token(token)
        try:
            validate_equal_passwords(password1, password2)
            validate_password_length(password2)
        except ValidationError as error:
            flash(error.message)
            return render_template('authentication/reset_password.html', user=user)
        user.set_password(password2)
        db.session.add(user)
        db.session.commit()
        flash('You password was successfully reset')
        return redirect(url_for('authentication.login'))


@auth_bp.route('/logout')
def logout():
    """Clears user`s id from session"""
    session.clear()
    flash('Successfully logged out')
    return redirect(url_for('view.index'))
