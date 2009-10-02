function showStuff() {
  var req = new XMLHttpRequest();
  req.open("GET", "/items", true);
  req.onreadystatechange = function() {
    if (req.readyState != 4) {
      return;
    }
    gotStuff(req.status, req.responseText);
  };
  req.send(null);
}

function gotStuff(status, text) {
  if (status != 200) {
    window.setTimeout(showStuff, 5000);
    return;
  }

  var content = "";
  var items = eval(text);
  if (items.length == 0) {
    content = "Nothing yet.\n"
  } else {
    content += "<ul>\n";	  
    for (var i = 0; i < items.length; ++i) {
      content += '<li class="lien"><big><a href="/user/' + items[i].author + '">@' + 
	items[i].author + '</a></big><div>' + items[i].content + '</div><small><a href="' +
	items[i].id + '">#' + items[i].id + '</a>, <span>' + items[i].date +
	" ago</span></small></li>\n";
    }
    content += "</ul>\n";	  
  }

  document.getElementById("entries").innerHTML = content;
  window.setTimeout(showStuff, 5000);
}

window.onload = showStuff;
